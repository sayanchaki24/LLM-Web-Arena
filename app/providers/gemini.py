import asyncio
import logging
from typing import Optional, Callable
from playwright.async_api import Page
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)

class GeminiProvider(BaseProvider):
    def __init__(self, url: str = "https://gemini.google.com/app"):
        super().__init__(name="Gemini", url=url)

    async def _dismiss_popups(self, page: Page):
        """Dismiss Google notices, cookie dialogs, or feature announcements."""
        for selector in [
            'button:has-text("I agree")',
            'button:has-text("Got it")',
            'button:has-text("Dismiss")',
            'button:has-text("Accept all")',
            'button[aria-label="Close"]',
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=500):
                    await btn.click()
                    await asyncio.sleep(0.3)
            except Exception:
                pass

    async def check_login_status(self, page: Page) -> bool:
        """Check if user has an active Gemini Google session with an interactive prompt box."""
        try:
            await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await self._dismiss_popups(page)

            # Check if sign in button is visible
            sign_in_btn = page.locator('button:has-text("Sign in"), a:has-text("Sign in"), a[href*="accounts.google.com"]').first
            is_signin_visible = False
            try:
                is_signin_visible = await sign_in_btn.is_visible(timeout=1000)
            except Exception:
                pass

            # Check if prompt editor exists
            prompt_editor = page.locator('rich-textarea div.ql-editor, div.ql-editor, div[contenteditable="true"]').first
            is_prompt_visible = False
            try:
                is_prompt_visible = await prompt_editor.is_visible(timeout=2000)
            except Exception:
                pass

            return is_prompt_visible and not is_signin_visible
        except Exception as e:
            logger.warning(f"Error checking Gemini login: {e}")
            return False

    async def send_prompt(
        self,
        page: Page,
        prompt: str,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> str:
        if progress_callback:
            progress_callback(self.name, "Navigating to Gemini...")

        await page.goto(self.url, wait_until="domcontentloaded", timeout=40000)
        await asyncio.sleep(2)
        await self._dismiss_popups(page)

        # Locate prompt editor
        input_selectors = [
            'rich-textarea div.ql-editor',
            'div.ql-editor[contenteditable="true"]',
            'div[contenteditable="true"][data-placeholder]',
            'rich-textarea',
            'div[contenteditable="true"]'
        ]

        target_input = None
        for sel in input_selectors:
            loc = page.locator(sel).first
            try:
                if await loc.is_visible(timeout=1500):
                    target_input = loc
                    break
            except Exception:
                continue

        if not target_input:
            raise RuntimeError("Gemini prompt input box not found. Please verify you are logged into your Google account.")

        if progress_callback:
            progress_callback(self.name, "Typing prompt...")

        await target_input.click()
        await asyncio.sleep(0.3)

        try:
            await target_input.fill(prompt)
        except Exception:
            await page.keyboard.insert_text(prompt)

        await asyncio.sleep(0.5)

        if progress_callback:
            progress_callback(self.name, "Submitting query...")

        assistant_selector = 'model-response, message-content, .model-response-text, div.markdown'
        prior_count = 0
        try:
            prior_count = await page.locator(assistant_selector).count()
        except Exception:
            pass

        send_btn = page.locator('button.send-button, button[aria-label*="Send message"], button[aria-label="Submit"]').first
        sent = False
        try:
            if await send_btn.is_enabled(timeout=1000):
                await send_btn.click()
                sent = True
        except Exception:
            pass

        if not sent:
            await page.keyboard.press("Enter")

        if progress_callback:
            progress_callback(self.name, "Waiting for Gemini to generate...")

        # Wait for new assistant message to appear
        for _ in range(30):
            await asyncio.sleep(0.5)
            try:
                curr_count = await page.locator(assistant_selector).count()
                if curr_count > prior_count:
                    break
            except Exception:
                pass

        async def get_latest_response():
            locators = page.locator(assistant_selector)
            count = await locators.count()
            if count > 0:
                last_el = locators.nth(count - 1)
                text = await last_el.inner_text()
                return text
            return ""

        stop_selector = 'button[aria-label*="Stop response"], button[aria-label*="Stop generating"]'
        response = await self.wait_for_text_stabilization(
            page=page,
            get_text_fn=get_latest_response,
            stop_selector=stop_selector,
            timeout=120,
            stabilize_seconds=3.0,
            progress_callback=progress_callback
        )

        return response
