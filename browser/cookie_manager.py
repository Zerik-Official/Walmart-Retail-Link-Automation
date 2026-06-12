import json
import os
from typing import List, Dict, Any

from browser.manager import BrowserManager
from utils.logger import log, Tags


COOKIES_FILE: str = "cookies/cookies.json"


async def load_cookies(manager: BrowserManager) -> bool:
    """Load cookies from disk and inject them into the browser context."""
    if not os.path.isfile(COOKIES_FILE):
        return False
    try:
        with open(COOKIES_FILE) as f:
            cookies: List[Dict[str, Any]] = json.load(f)
        if not cookies:
            return False
        await manager.add_cookies(cookies)
        log("INFO", Tags.SYSTEM, f"Loaded {len(cookies)} cookies from {COOKIES_FILE}")
        return True
    except Exception as e:
        log("WARNING", Tags.SYSTEM, f"Failed to load cookies: {e}")
        return False


async def save_cookies(manager: BrowserManager) -> None:
    """Export cookies from the browser context and save them to disk."""
    try:
        cookies = await manager.get_cookies()
        os.makedirs(os.path.dirname(COOKIES_FILE), exist_ok=True)
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f, indent=2)
        log("SUCCESS", Tags.SYSTEM, f"Saved {len(cookies)} cookies to {COOKIES_FILE}")
    except Exception as e:
        log("WARNING", Tags.SYSTEM, f"Failed to save cookies: {e}")
