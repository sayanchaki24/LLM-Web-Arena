import asyncio
import logging
from typing import Optional, Callable
from playwright.async_api import Page
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)

class ClaudeProvider(BaseProvider):
    def __init__(self, url: str = "https://claude.ai/new"):
        super().__init__(name="Claude", url=url)

    async def _dismiss_popups(self, page: Page):
        """Dismiss common modals, cookie banners, or onboarding prompts."""
        for selector in [
            'button:has-text("Acknowledge")',
            'button:has-text("Accept")',
            'button:has-text("Got it")',
            'button:has-text("Continue")',
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
        """Check if user has an active Claude session with an interactive input."""
        try:
            await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            await self._dismiss_popups(page)

            # Wait briefly if Cloudflare is resolving
            for _ in range(8):
                title = await page.title()
                if "just a moment" in title.lower() or "security" in title.lower():
                    await asyncio.sleep(1)
                else:
                    break

            # Check if login / email field is displayed
            login_field = page.locator('input[type="email"], button:has-text("Continue with Google"), a[href*="login"]').first
            is_login_visible = False
            try:
                is_login_visible = await login_field.is_visible(timeout=1000)
            except Exception:
                pass

            # Check if prompt box exists
            prompt_box = page.locator('div.ProseMirror, fieldset div[contenteditable="true"], div[contenteditable="true"]').first
            is_prompt_visible = False
            try:
                is_prompt_visible = await prompt_box.is_visible(timeout=6000)
            except Exception:
                pass

            return is_prompt_visible and not is_login_visible
        except Exception as e:
            logger.warning(f"Error checking Claude login: {e}")
            return False

    async def send_prompt(
        self,
        page: Page,
        prompt: str,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> str:
        if progress_callback:
            progress_callback(self.name, "Navigating to Claude...")

        await page.goto(self.url, wait_until="domcontentloaded", timeout=40000)
        await asyncio.sleep(2)
        await self._dismiss_popups(page)

        # Wait if Cloudflare Turnstile challenge is active
        for _ in range(12):
            title = await page.title()
            if "just a moment" in title.lower() or "security" in title.lower():
                if progress_callback:
                    progress_callback(self.name, "Waiting for security verification...")
                await asyncio.sleep(1.5)
            else:
                break

        # Locate prompt textarea with up to 15s wait
        input_selectors = [
            'div.ProseMirror',
            'fieldset div[contenteditable="true"]',
            'div[contenteditable="true"]',
            'p[data-placeholder]',
            'div[data-placeholder*="Claude"]'
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
            raise RuntimeError("Claude prompt input box not found. Please verify you are logged in and Cloudflare challenge is passed.")

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
            prior_count = await page.evaluate('''() => {
                return document.querySelectorAll('.font-claude-message, [data-testid="chat-message-assistant"], .standard-markdown, [data-is-streaming]').length;
            }''')
        except Exception:
            pass

        if progress_callback:
            progress_callback(self.name, "Submitting query...")

        send_btn = page.locator('button[aria-label*="Send" i], button[data-testid="send-button"], fieldset button:has(svg)').last
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
            progress_callback(self.name, "Waiting for Claude to generate...")

        # Wait for generation to start (up to 30s)
        stop_selector = 'button[aria-label*="Stop" i], button:has-text("Stop responding")'
        for _ in range(30):
            await asyncio.sleep(1)
            try:
                curr_count = await page.evaluate('''() => {
                    return document.querySelectorAll('.font-claude-message, [data-testid="chat-message-assistant"], .standard-markdown, [data-is-streaming]').length;
                }''')
                stop_btn = page.locator(stop_selector).first
                if curr_count > prior_count or await stop_btn.is_visible(timeout=200):
                    break
            except Exception:
                pass

        async def get_latest_response():
            # Extract the actual assistant message body, stripping action toolbars (Copy/Retry buttons)
            res = await page.evaluate('''() => {
                const candidates = Array.from(document.querySelectorAll('.font-claude-message, [data-testid="chat-message-assistant"], .standard-markdown, [data-is-streaming]'));
                if (candidates.length === 0) return "";
                const last = candidates[candidates.length - 1];
                const clone = last.cloneNode(true);
                // Remove toolbar buttons and utility controls
                clone.querySelectorAll('button, .flex.gap-2, .font-user-message').forEach(el => el.remove());
                return clone.innerText.trim();
            }''')
            return res or ""

        response = await self.wait_for_text_stabilization(
            page=page,
            get_text_fn=get_latest_response,
            stop_selector=stop_selector,
            timeout=140,
            stabilize_seconds=3.5,
            progress_callback=progress_callback
        )

        return response
