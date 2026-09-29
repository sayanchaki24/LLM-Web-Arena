import os
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable
from playwright.async_api import async_playwright, BrowserContext, Page
from app.config import settings
from app.providers import PROVIDERS, BaseProvider
from app.evaluator import compute_heuristics, build_judge_prompt, parse_judge_verdict
from app.database import save_query_record, save_response_record, update_query_evaluation

logger = logging.getLogger(__name__)

class BrowserManager:
    def __init__(self):
        self.profile_dir = str(settings.profile_dir.resolve())
        self._login_context: Optional[BrowserContext] = None
        self._playwright_instance = None
        self._lock = asyncio.Lock()

    def _get_browser_args(self) -> List[str]:
        return [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--start-maximized"
        ]

    async def open_login_window(self) -> Dict[str, str]:
        """
        Launches a headed browser window with tabs for ChatGPT, Claude, and Gemini
        so the user can manually log in with 2FA/SSO.
        """
        async with self._lock:
            if self._login_context:
                return {"status": "already_open", "message": "Login browser is already open."}

            try:
                pw = await async_playwright().start()
                self._playwright_instance = pw
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    headless=False,
                    no_viewport=True,
                    ignore_default_args=["--enable-automation"],
                    args=self._get_browser_args(),
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                )
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = { runtime: {} };
                """)
                self._login_context = context

                # Open ChatGPT, Claude, Gemini tabs
                page1 = context.pages[0] if context.pages else await context.new_page()
                await page1.goto(settings.chatgpt_url)

                page2 = await context.new_page()
                await page2.goto(settings.claude_url)

                page3 = await context.new_page()
                await page3.goto(settings.gemini_url)

                page4 = await context.new_page()
                await page4.goto("https://chat.z.ai/auth")

                return {
                    "status": "success",
                    "message": "Login browser window opened with ChatGPT, Claude, Gemini, and GLM tabs."
                }
            except Exception as e:
                logger.error(f"Failed to open login window: {e}")
                if self._playwright_instance:
                    await self._playwright_instance.stop()
                    self._playwright_instance = None
                self._login_context = None
                return {"status": "error", "message": str(e)}

    async def close_login_window(self) -> Dict[str, str]:
        """Closes the interactive login window and persists session cookies."""
        async with self._lock:
            if not self._login_context:
                return {"status": "not_open", "message": "No login window is currently open."}
            try:
                await self._login_context.close()
                if self._playwright_instance:
                    await self._playwright_instance.stop()
                self._login_context = None
                self._playwright_instance = None
                return {"status": "success", "message": "Login window closed. Session saved."}
            except Exception as e:
                logger.error(f"Error closing login window: {e}")
                return {"status": "error", "message": str(e)}

    async def check_all_logins(self) -> Dict[str, Any]:
        """Checks authentication status for each provider."""
        async with self._lock:
            # If login window is currently open, we must not conflict on the profile folder
            if self._login_context:
                return {
                    "ChatGPT": {"logged_in": True, "status": "Browser window is currently active"},
                    "Claude": {"logged_in": True, "status": "Browser window is currently active"},
                    "Gemini": {"logged_in": True, "status": "Browser window is currently active"},
                    "GLM": {"logged_in": True, "status": "Browser window is currently active"}
                }

            results = {}
            pw = await async_playwright().start()
            try:
                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    headless=settings.headless,
                    ignore_default_args=["--enable-automation"],
                    args=self._get_browser_args(),
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                )
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = { runtime: {} };
                """)

                for name, provider in PROVIDERS.items():
                    try:
                        page = await context.new_page()
                        is_logged_in = await provider.check_login_status(page)
                        await page.close()
                        results[name] = {
                            "logged_in": is_logged_in,
                            "status": "Ready" if is_logged_in else "Not logged in"
                        }
                    except Exception as e:
                        results[name] = {"logged_in": False, "status": f"Check error: {str(e)[:50]}"}

                await context.close()
            finally:
                await pw.stop()

            return results

    async def run_multi_query(
        self,
        prompt: str,
        selected_models: List[str],
        judge_model_choice: str = "Gemini",
        headless: bool = False,
        progress_callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes the user prompt across all requested models in parallel,
        collects responses, runs AI peer evaluation, and returns complete analysis.
        """
        async with self._lock:
            # Close existing login context if left open
            if self._login_context:
                try:
                    await self._login_context.close()
                    if self._playwright_instance:
                        await self._playwright_instance.stop()
                except Exception:
                    pass
                self._login_context = None
                self._playwright_instance = None

            pw = await async_playwright().start()
            context = None
            try:
                if progress_callback:
                    progress_callback("System", "Initializing browser engine...")

                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=self.profile_dir,
                    headless=headless,
                    no_viewport=True,
                    ignore_default_args=["--enable-automation"],
                    args=self._get_browser_args(),
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
                )
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = { runtime: {} };
                """)

                # Step 1: Create tasks for each selected model
                tasks = []
                active_providers: Dict[str, BaseProvider] = {}
                pages_map: Dict[str, Page] = {}

                for model_name in selected_models:
                    if model_name in PROVIDERS:
                        provider = PROVIDERS[model_name]
                        active_providers[model_name] = provider
                        page = await context.new_page()
                        pages_map[model_name] = page

                if not active_providers:
                    raise ValueError("No valid models selected for query.")

                if progress_callback:
                    progress_callback("System", f"Dispatching prompt to {len(active_providers)} models in parallel...")

                async def query_single_model(name: str, prov: BaseProvider, page: Page):
                    t0 = time.time()
                    try:
                        resp_text = await prov.send_prompt(page, prompt, progress_callback=progress_callback)
                        elapsed = round(time.time() - t0, 2)
                        heuristics = compute_heuristics(resp_text)
                        if progress_callback:
                            progress_callback(name, f"Completed in {elapsed}s ({heuristics['word_count']} words)")
                        return {
                            "model_name": name,
                            "response_text": resp_text,
                            "status": "success",
                            "error_message": None,
                            "elapsed_seconds": elapsed,
                            **heuristics
                        }
                    except Exception as err:
                        elapsed = round(time.time() - t0, 2)
                        logger.error(f"Error querying {name}: {err}")
                        if progress_callback:
                            progress_callback(name, f"Failed: {str(err)[:60]}")
                        return {
                            "model_name": name,
                            "response_text": None,
                            "status": "error",
                            "error_message": str(err),
                            "elapsed_seconds": elapsed,
                            **compute_heuristics("")
                        }

                # Run queries concurrently
                coros = [query_single_model(name, prov, pages_map[name]) for name, prov in active_providers.items()]
                results_list = await asyncio.gather(*coros)

                # Step 2: Separate successful responses
                successful_responses = {
                    r["model_name"]: r["response_text"]
                    for r in results_list
                    if r["status"] == "success" and r["response_text"]
                }

                # Step 3: Run AI Peer Evaluation if 2 or more succeeded
                winner = None
                evaluation_summary = None
                judge_reason = None
                actual_judge = judge_model_choice

                if len(successful_responses) >= 2:
                    if progress_callback:
                        progress_callback("Judge", f"Preparing anonymized AI evaluation using {actual_judge}...")

                    # Pick judge provider
                    judge_provider = active_providers.get(actual_judge)

                    # Fallback to any successful model if requested judge failed
                    if not judge_provider or actual_judge not in successful_responses:
                        actual_judge = list(successful_responses.keys())[0]
                        judge_provider = active_providers[actual_judge]

                    judge_prompt, mapping = build_judge_prompt(prompt, successful_responses)

                    try:
                        if progress_callback:
                            progress_callback("Judge", f"AI Judge ({actual_judge}) analyzing candidate answers...")

                        # Open dedicated fresh page for judge to avoid conversation history/DOM collisions
                        judge_page = await context.new_page()
                        try:
                            judge_response = await judge_provider.send_prompt(
                                judge_page,
                                judge_prompt,
                                progress_callback=lambda m, s: progress_callback("Judge", s) if progress_callback else None
                            )
                        finally:
                            try:
                                await judge_page.close()
                            except Exception:
                                pass

                        verdict = parse_judge_verdict(judge_response, mapping)
                        winner = verdict["winner"]
                        judge_reason = verdict["reason"]
                        evaluation_summary = verdict["evaluation_summary"]

                        if progress_callback:
                            progress_callback("Judge", f"Evaluation complete! Winner: {winner}")

                    except Exception as judge_err:
                        logger.error(f"AI Judge failed: {judge_err}")
                        # Fallback to heuristic highest score
                        best_candidate = max(results_list, key=lambda x: x.get("heuristic_score", 0))
                        winner = best_candidate["model_name"]
                        judge_reason = f"Selected by quantitative heuristic score ({best_candidate.get('heuristic_score')} pts) due to judge timeout."
                        evaluation_summary = f"Automated scoring awarded {winner} the top rating based on structure, depth, and density."

                elif len(successful_responses) == 1:
                    winner = list(successful_responses.keys())[0]
                    judge_reason = "Single successful model response."
                    evaluation_summary = f"Only {winner} returned a response for this query."
                else:
                    winner = None
                    judge_reason = "No models returned successful responses."
                    evaluation_summary = "All selected models failed or were not logged in. Please check browser logins."

                # Step 4: Persist in SQLite
                query_id = save_query_record(
                    prompt=prompt,
                    models_queried=selected_models,
                    judge_model=actual_judge if len(successful_responses) >= 2 else None,
                    winner=winner,
                    evaluation_summary=evaluation_summary,
                    judge_reason=judge_reason
                )

                for r in results_list:
                    save_response_record(
                        query_id=query_id,
                        model_name=r["model_name"],
                        response_text=r["response_text"],
                        status=r["status"],
                        error_message=r["error_message"],
                        word_count=r.get("word_count", 0),
                        char_count=r.get("char_count", 0),
                        code_blocks=r.get("code_blocks", 0),
                        elapsed_seconds=r.get("elapsed_seconds", 0.0)
                    )

                return {
                    "query_id": query_id,
                    "prompt": prompt,
                    "winner": winner,
                    "judge_model": actual_judge if len(successful_responses) >= 2 else None,
                    "judge_reason": judge_reason,
                    "evaluation_summary": evaluation_summary,
                    "results": results_list
                }

            finally:
                if context:
                    await context.close()
                await pw.stop()

browser_manager = BrowserManager()
