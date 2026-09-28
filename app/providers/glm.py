import asyncio
import logging
from typing import Optional, Callable
from playwright.async_api import Page
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)

class GLMProvider(BaseProvider):
    def __init__(self, url: str = "https://chat.z.ai/"):
        super().__init__(name="GLM", url=url)

    async def _dismiss_popups(self, page: Page):
        """Dismiss common modals, announcements, cookie notices, or onboarding prompts."""
        for selector in [
            'button:has-text("Got it")',
            'button:has-text("Accept")',
            'button:has-text("Agree")',
            'button:has-text("Confirm")',
            'button:has-text("Dismiss")',
            'button:has-text("我知道了")',
            'button:has-text("同意")',
            'button[aria-label="Close"]',
            'button[aria-label="close"]',
        ]:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=500):
                    await btn.click()
                    await asyncio.sleep(0.3)
            except Exception:
                pass

    async def check_login_status(self, page: Page) -> bool:
        """Check if user has an active GLM (chat.z.ai) session with an interactive input."""
        try:
            await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await self._dismiss_popups(page)

            # Check if login/sign-in button is displayed prominently
            login_btn = page.locator(
                'button:has-text("Log in"), button:has-text("Sign in"), button:has-text("Login"), button:has-text("登录"), a[href*="login"], a[href*="signin"]'
            ).first
            is_login_visible = False
            try:
                is_login_visible = await login_btn.is_visible(timeout=1000)
            except Exception:
                pass

            # Check if prompt input exists
            input_box = page.locator(
                '#chat-input, textarea, div[contenteditable="true"]'
            ).first
            is_prompt_visible = False
            try:
                is_prompt_visible = await input_box.is_visible(timeout=2000)
            except Exception:
                pass

            return is_prompt_visible and not is_login_visible
        except Exception as e:
            logger.warning(f"Error checking GLM login: {e}")
            return False

    async def send_prompt(
        self,
        page: Page,
        prompt: str,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> str:
        if progress_callback:
            progress_callback(self.name, "Navigating to GLM (chat.z.ai)...")

        await page.goto(self.url, wait_until="domcontentloaded", timeout=40000)
        await asyncio.sleep(2)
        await self._dismiss_popups(page)

        # Locate prompt textarea / input
        input_selectors = [
            '#chat-input',
            'textarea[placeholder*="Ask"]',
            'textarea[placeholder*="chat"]',
            'textarea',
            'div[contenteditable="true"]#chat-input',
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
            raise RuntimeError("GLM prompt input box not found. Please verify you are logged into https://chat.z.ai/.")

        if progress_callback:
            progress_callback(self.name, "Typing prompt into GLM...")

        await target_input.click()
        await asyncio.sleep(0.3)

        try:
            await target_input.fill(prompt)
        except Exception:
            await page.keyboard.insert_text(prompt)

        await asyncio.sleep(0.5)

        if progress_callback:
            progress_callback(self.name, "Submitting query to GLM...")

        # Count prior assistant messages
        assistant_selectors = [
            '[data-message-author-role="assistant"]',
            '.markdown',
            '.assistant-message',
            'div[class*="message"][class*="assistant"]',
            'div[class*="chat-message"]:not([class*="user"])'
        ]
        
        # Pick the active selector or fallback to .markdown
        assistant_selector = '.markdown, [data-message-author-role="assistant"], div[class*="message"]:not([class*="user"])'
        prior_count = 0
        try:
            prior_count = await page.locator(assistant_selector).count()
        except Exception:
            pass

        # Locate and click send button
        send_selectors = [
            'button[data-testid="send-button"]',
            'button[aria-label*="Send"]',
            'button[aria-label*="发送"]',
            'button:has(svg):not([disabled])'
        ]
        sent = False
        for send_sel in send_selectors:
            try:
                btn = page.locator(send_sel).last
                if await btn.is_enabled(timeout=1000):
                    await btn.click()
                    sent = True
                    break
            except Exception:
                continue

        if not sent:
            await page.keyboard.press("Enter")

        if progress_callback:
            progress_callback(self.name, "Waiting for GLM to generate...")

        # Wait for new message to appear
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

        stop_selector = 'button[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="停止"]'
        response = await self.wait_for_text_stabilization(
            page=page,
            get_text_fn=get_latest_response,
            stop_selector=stop_selector,
            timeout=140,
            stabilize_seconds=3.0,
            progress_callback=progress_callback
        )

        return response
