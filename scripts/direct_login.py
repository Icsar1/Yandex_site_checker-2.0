"""
Interactive headed login to Yandex for Direct forecast automation.

Usage:
    python scripts/direct_login.py

The script opens a visible Chromium browser at the Yandex Direct forecast page.
You log in manually (handle captcha/2FA yourself).
Once the page loads successfully, press Enter in the terminal to save the session.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings

DIRECT_URL = "https://direct.yandex.ru/registered/main.pl?cmd=advancedForecast"
STORAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "storage_state.json"


async def main():
    settings = get_settings()

    # Use login/password from .env for initial pre-fill hint
    login = settings.YANDEX_DIRECT_LOGIN.get_secret_value()

    print("=== Yandex Direct Login ===")
    print(f"Target: {DIRECT_URL}")
    print(f"Storage state will be saved to: {STORAGE_PATH}")
    if login:
        print(f"Login hint: {login}")
    print()

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print("Opening Direct forecast page...")
        await page.goto(DIRECT_URL, wait_until="domcontentloaded", timeout=30000)

        current_url = page.url
        print(f"Current URL: {current_url}")

        if "passport" in current_url.lower():
            print("\nYou are on the Yandex Passport login page.")
            print("Please log in manually in the browser window.")
            print("Handle captcha/2FA as needed.")
        else:
            print("\nYou appear to be already logged in.")

        print("\n>>> After you are logged in and see the Direct forecast page,")
        print(">>> press ENTER here to save the session.")

        # Wait for user input (blocking)
        await asyncio.get_event_loop().run_in_executor(None, input)

        # Save storage state
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(STORAGE_PATH))
        print(f"\nSession saved to: {STORAGE_PATH}")
        print(f"File size: {STORAGE_PATH.stat().st_size} bytes")

        await browser.close()

    print("\nDone! You can now run the pipeline with MOCK_YANDEX=false.")


if __name__ == "__main__":
    asyncio.run(main())
