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
                is_prompt_visible = await prompt_editor.is_visible(timeout=6000)
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

        # Locate prompt editor with up to 15s wait
        input_selectors = [
            'rich-textarea div.ql-editor',
            'div.ql-editor[contenteditable="true"]',
            'rich-textarea',
            'div[contenteditable="true"][data-placeholder]',
            'div[contenteditable="true"]'
        ]

        target_input = None
        for _ in range(15):
            for sel in input_selectors:
                loc = page.locator(sel).first
                try:
                    if await loc.is_visible(timeout=500):
                        target_input = loc
                        break
                except Exception:
                    continue
            if target_input:
                break
            await asyncio.sleep(1)

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

        # Count prior assistant messages
        prior_count = 0
        try:
            prior_count = await page.locator('message-content').count()
        except Exception:
            pass

        if progress_callback:
            progress_callback(self.name, "Submitting query...")

        send_selectors = [
            'button[aria-label*="Send message" i]',
            'button.send-button',
            'button[aria-label="Submit" i]'
        ]
        sent = False
        for send_sel in send_selectors:
            try:
                btn = page.locator(send_sel).first
                if await btn.is_enabled(timeout=1000):
                    await btn.click()
                    sent = True
                    break
            except Exception:
                continue

        if not sent:
            await page.keyboard.press("Enter")

        if progress_callback:
            progress_callback(self.name, "Waiting for Gemini to generate...")

        # Wait for generation to start (up to 35 seconds)
        stop_selector = 'button[aria-label*="Stop response" i], button[aria-label*="Stop generating" i], button[aria-label*="Stop" i]'
        for _ in range(35):
            await asyncio.sleep(1)
            try:
                curr_count = await page.locator('message-content').count()
                stop_btn = page.locator(stop_selector).first
                is_generating = await stop_btn.is_visible(timeout=300)
                if curr_count > prior_count or is_generating:
                    break
            except Exception:
                pass

        async def get_latest_response():
            # Query message-content directly so full markdown text is retrieved
            locators = page.locator('message-content')
            count = await locators.count()
            if count > 0:
                text = await locators.nth(count - 1).inner_text()
                if text and len(text.strip()) > 0:
                    return text.strip()

            # Fallback to model-response
            mr_locators = page.locator('model-response')
            mr_count = await mr_locators.count()
            if mr_count > 0:
                mr_text = await mr_locators.nth(mr_count - 1).inner_text()
                if mr_text.startswith("Gemini said"):
                    mr_text = mr_text.replace("Gemini said", "", 1).strip()
                return mr_text.strip()

            return ""

        response = await self.wait_for_text_stabilization(
            page=page,
            get_text_fn=get_latest_response,
            stop_selector=stop_selector,
            timeout=120,
            stabilize_seconds=3.0,
            progress_callback=progress_callback
        )

        return response
