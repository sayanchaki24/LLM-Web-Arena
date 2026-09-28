import time
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Callable
from playwright.async_api import Page

class BaseProvider(ABC):
    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url

    @abstractmethod
    async def check_login_status(self, page: Page) -> bool:
        """Return True if the user is authenticated and the chat input is accessible."""
        pass

    @abstractmethod
    async def send_prompt(
        self,
        page: Page,
        prompt: str,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> str:
        """Send the prompt, wait for generation to complete, and return the response text."""
        pass

    async def wait_for_text_stabilization(
        self,
        page: Page,
        get_text_fn: Callable[[], str],
        stop_selector: Optional[str] = None,
        timeout: int = 150,
        stabilize_seconds: float = 3.0,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> str:
        """
        Monitors text output until it stops growing for `stabilize_seconds` and
        the stop-generating button (if any) disappears.
        """
        start_time = time.time()
        last_text = ""
        last_change_time = time.time()
        has_started = False

        while time.time() - start_time < timeout:
            await asyncio.sleep(0.6)
            try:
                current_text = await get_text_fn()
            except Exception:
                current_text = last_text

            if current_text and len(current_text.strip()) > 0:
                if not has_started:
                    has_started = True
                    if progress_callback:
                        progress_callback(self.name, "Receiving response...")

                if current_text != last_text:
                    last_text = current_text
                    last_change_time = time.time()
                    if progress_callback and len(current_text) % 80 < 15:
                        words = len(current_text.split())
                        progress_callback(self.name, f"Generating... ({words} words)")
                else:
                    # Check if stop button is still present
                    is_still_generating = False
                    if stop_selector:
                        try:
                            stop_btn = page.locator(stop_selector).first
                            if await stop_btn.is_visible(timeout=300):
                                is_still_generating = True
                        except Exception:
                            pass

                    # Text has not changed for stabilize_seconds and stop button is gone
                    if (time.time() - last_change_time >= stabilize_seconds) and not is_still_generating:
                        if len(last_text.strip()) > 10:
                            return last_text.strip()

        if last_text and len(last_text.strip()) > 10:
            return last_text.strip()

        raise TimeoutError(f"Timed out waiting for response from {self.name} after {timeout}s.")
