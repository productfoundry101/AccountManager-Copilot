"""Visit the Streamlit app with a real browser and wake it if it is asleep.

Streamlit Community Cloud sleeps an app after 12 hours without traffic. A plain
HTTP ping returns 200 on the sleep page and does NOT wake the app, so we drive a
headless Chromium via Playwright: load the page, and if the "get this app back
up" button is present, click it. Either way, the visit resets the sleep timer.
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "").strip()
if not URL:
    print("APP_URL is not set."); sys.exit(1)

WAKE_LABELS = [
    "Yes, get this app back up!",
    "get this app back up",
    "Yes, get this app back up",
]


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        print(f"Visiting {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=120_000)
        time.sleep(5)  # let the sleep page (if any) render

        woke = False
        for label in WAKE_LABELS:
            try:
                btn = page.get_by_text(label, exact=False)
                if btn.count() > 0:
                    btn.first.click()
                    woke = True
                    print("App was asleep. Clicked the wake button.")
                    break
            except Exception as exc:  # keep going, the visit alone resets the timer
                print(f"  (wake-button check '{label}' skipped: {exc})")

        # Give it time to boot if we woke it, otherwise just settle.
        time.sleep(45 if woke else 10)
        try:
            print(f"Done. Page title: {page.title()!r}. Woke: {woke}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
