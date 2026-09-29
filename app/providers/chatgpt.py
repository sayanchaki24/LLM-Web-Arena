import asyncio
import logging
from typing import Optional, Callable
from playwright.async_api import Page
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)

class ChatGPTProvider(BaseProvider):
    def __init__(self, url: str = "https://chatgpt.com/"):
        super().__init__(name="ChatGPT", url=url)

    async def _dismiss_popups(self, page: Page):
        """Dismiss common modals, cookie banners, or onboarding prompts."""
        for selector in [
            'button:has-text("Stay logged out")',
            'button:has-text("Got it")',
            'button:has-text("Dismiss")',
            'button[aria-label="Close"]',
            'button:has-text("Accept all")',
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=500):
                    await btn.click()
                    await asyncio.sleep(0.3)
            except Exception:
                pass

    async def check_login_status(self, page: Page) -> bool:
        """Check if user has an active ChatGPT session with an interactive input."""
        try:
            await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await self._dismiss_popups(page)

            # Check if login button is displayed without prompt box
            login_btn = page.locator('button:has-text("Log in"), a[href*="login"], [data-testid="login-button"]').first
            is_login_visible = False
            try:
                is_login_visible = await login_btn.is_visible(timeout=1000)
            except Exception:
                pass

            # Check if prompt textarea exists
            prompt_box = page.locator('#prompt-textarea, div[contenteditable="true"]#prompt-textarea, textarea[data-id="root"]').first
            is_prompt_visible = False
            try:
                is_prompt_visible = await prompt_box.is_visible(timeout=2000)
            except Exception:
                pass

            return is_prompt_visible and not is_login_visible
        except Exception as e:
            logger.warning(f"Error checking ChatGPT login: {e}")
            return False

    async def send_prompt(
        self,
        page: Page,
        prompt: str,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> str:
        if progress_callback:
            progress_callback(self.name, "Navigating to ChatGPT...")

        await page.goto(self.url, wait_until="domcontentloaded", timeout=40000)
        await asyncio.sleep(2)
        await self._dismiss_popups(page)

        # Locate prompt textarea
        input_selectors = [
            '#prompt-textarea',
            'div[contenteditable="true"]#prompt-textarea',
            'div[contenteditable="true"][data-placeholder]',
            'textarea[data-id="root"]',
            'textarea'
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
            raise RuntimeError("ChatGPT prompt input box not found. Please verify you are logged in.")

        if progress_callback:
            progress_callback(self.name, "Typing prompt...")

        await target_input.click()
        await asyncio.sleep(0.3)

        # Safe input injection compatible with React / ProseMirror
        try:
            await target_input.fill(prompt)
        except Exception:
            # Fallback for contenteditable div
            await page.keyboard.insert_text(prompt)

        await asyncio.sleep(0.5)

        if progress_callback:
            progress_callback(self.name, "Submitting query...")

        # Count prior assistant messages
        assistant_selector = '[data-message-author-role="assistant"], article [data-message-author-role="assistant"], .markdown'
        prior_count = 0
        try:
            prior_count = await page.locator(assistant_selector).count()
        except Exception:
            pass

        # Submit via Enter or Send button
        send_btn = page.locator('button[data-testid="send-button"], button[aria-label="Send prompt"]').first
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
            progress_callback(self.name, "Waiting for ChatGPT to generate...")

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

        stop_selector = 'button[data-testid="stop-button"], button[aria-label*="Stop"]'
        response = await self.wait_for_text_stabilization(
            page=page,
            get_text_fn=get_latest_response,
            stop_selector=stop_selector,
            timeout=120,
            stabilize_seconds=3.0,
            progress_callback=progress_callback
        )

        return response
