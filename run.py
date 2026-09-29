import sys
import os
import argparse
import asyncio
import webbrowser
import uvicorn
from app.config import settings
from app.browser_manager import browser_manager

def main():
    parser = argparse.ArgumentParser(description="BestResponse - Multi-LLM Web Orchestrator & AI Judge")
    parser.add_argument("--login", action="store_true", help="Launch persistent browser window to log in to ChatGPT, Claude, and Gemini accounts")
    parser.add_argument("--host", default=settings.host, help="Host address to bind server (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=settings.port, help="Port to bind server (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open web browser on launch")
    args = parser.parse_args()

    if args.login:
        print("\n=======================================================")
        print("  BestResponse: Interactive Web Login Manager")
        print("=======================================================")
        print("Opening Chromium browser window with tabs for:")
        print("  1. ChatGPT (https://chatgpt.com/)")
        print("  2. Claude (https://claude.ai/new)")
        print("  3. Gemini (https://gemini.google.com/app)")
        print("  4. GLM (https://chat.z.ai/)")
        print("\nPlease sign in to your accounts. Your session cookies and tokens")
        print(f"will be permanently saved in: {settings.profile_dir}")
        print("Close the browser window when you are done logging in.\n")

        async def run_login_flow():
            res = await browser_manager.open_login_window()
            print(res["message"])
            print("\nWaiting for browser window to close...")
            # Keep process alive while context is open
            while browser_manager._login_context:
                await asyncio.sleep(1)

        asyncio.run(run_login_flow())
        print("\nLogin session finished! You can now start the server: python run.py\n")
        return

    dashboard_url = f"http://{args.host}:{args.port}"
    print("\n=======================================================")
    print("  🚀 BestResponse Multi-LLM Web Aggregator & AI Judge")
    print("=======================================================")
    print(f"  • Dashboard URL: {dashboard_url}")
    print(f"  • Persistent Profile: {settings.profile_dir}")
    print(f"  • Database: {settings.db_path}")
    print("=======================================================\n")

    if not args.no_browser:
        # Schedule browser open after uvicorn initializes
        import threading
        threading.Timer(1.5, lambda: webbrowser.open(dashboard_url)).start()

    uvicorn.run("app.server:app", host=args.host, port=args.port, reload=False, log_level="info", ws="auto")

if __name__ == "__main__":
    main()
