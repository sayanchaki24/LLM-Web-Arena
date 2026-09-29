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

            # 1. Fast token payload check from localStorage
            try:
                user_info = await page.evaluate('''() => {
                    try {
                        const tok = localStorage.getItem("token");
                        if (!tok) return null;
                        const parts = tok.split(".");
                        if (parts.length < 2) return null;
                        const payload = JSON.parse(atob(parts[1]));
                        return payload;
                    } catch (e) {
                        return null;
                    }
                }''')
                if user_info and isinstance(user_info, dict):
                    email = user_info.get("email", "")
                    # Real registered accounts do not use guest-*@guest.com
                    if email and not email.startswith("guest-") and "@guest." not in email:
                        logger.info(f"GLM logged in with verified user token: {email}")
                        return True
            except Exception as e:
                logger.debug(f"GLM token decode check: {e}")

            # 2. Check if login/sign-in button is displayed prominently
            login_btn = page.locator(
                'button:has-text("Sign in"), button:has-text("Log in"), button:has-text("Login"), button:has-text("登录"), a[href*="login"], a[href*="signin"], a[href*="auth"]'
            ).first
            is_login_visible = False
            try:
                is_login_visible = await login_btn.is_visible(timeout=2000)
            except Exception:
                pass

            # 3. Check if prompt input exists
            input_box = page.locator(
                '#chat-input, textarea.input-scroll, textarea, div[contenteditable="true"]'
            ).first
            is_prompt_visible = False
            try:
                is_prompt_visible = await input_box.is_visible(timeout=6000)
            except Exception:
                pass

            logger.info(f"GLM check_login_status: url={page.url} is_prompt={is_prompt_visible} is_login_vis={is_login_visible}")
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

        # Locate prompt textarea / input with up to 15s wait
        input_selectors = [
            '#chat-input',
            'textarea.input-scroll',
            'textarea',
            'div[contenteditable="true"]#chat-input',
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

        # Count prior assistant messages
        prior_count = 0
        try:
            prior_count = await page.evaluate('''() => {
                return document.querySelectorAll('div[class*="message-"]:not(.user-message):not([class*="messageInputContainer"]), .markdown').length;
            }''')
        except Exception:
            pass

        if progress_callback:
            progress_callback(self.name, "Submitting query to GLM...")

        send_selectors = [
            '#send-message-button',
            '.sendMessageButton',
            'button[type="submit"]',
            'button[data-testid="send-button"]',
            'button[aria-label*="Send" i]',
            'button[aria-label*="发送"]'
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
            progress_callback(self.name, "Waiting for GLM to generate...")

        # Wait for generation to start (up to 35 seconds to allow Deep Think initialization)
        for _ in range(35):
            await asyncio.sleep(1)
            try:
                curr_count = await page.evaluate('''() => {
                    return document.querySelectorAll('div[class*="message-"]:not(.user-message):not([class*="messageInputContainer"]), .markdown').length;
                }''')
                # If send button is disabled/replaced by stop icon, generation has started
                stop_btn = page.locator('button[aria-label*="stop" i], button[aria-label*="停止"], .stop-btn').first
                if curr_count > prior_count or await stop_btn.is_visible(timeout=200):
                    break
            except Exception:
                pass

        async def get_latest_response():
            # Robust extraction of assistant message excluding input container and user messages
            res = await page.evaluate('''() => {
                // Find all candidate message blocks that are NOT user messages and NOT the input container
                const candidates = Array.from(document.querySelectorAll('div[class*="message-"]')).filter(
                    d => !d.className.includes('user-message') && !d.className.includes('messageInputContainer')
                );
                if (candidates.length > 0) {
                    const last = candidates[candidates.length - 1];
                    const md = last.querySelector('.markdown') || last.querySelector('.prose');
                    if (md && md.innerText.trim().length > 0) {
                        return md.innerText.trim();
                    }
                    const text = last.innerText.trim();
                    if (text.length > 0 && !text.includes('messageInputContainer')) {
                        return text;
                    }
                }
                const markdowns = Array.from(document.querySelectorAll('.markdown'));
                if (markdowns.length > 0) {
                    return markdowns[markdowns.length - 1].innerText.trim();
                }
                return "";
            }''')
            # Protect against capturing "Deep Think\nMax" or UI badge text
            if res and len(res) > 0:
                clean = res.strip()
                if clean in ["Deep Think", "Deep Think\nMax", "Max"]:
                    return ""
                return clean
            return ""

        stop_selector = 'button[aria-label*="stop" i], button[aria-label*="停止"], .stop-btn'
        response = await self.wait_for_text_stabilization(
            page=page,
            get_text_fn=get_latest_response,
            stop_selector=stop_selector,
            timeout=140,
            stabilize_seconds=3.5,
            progress_callback=progress_callback
        )

        return response
