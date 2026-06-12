import random
from pathlib import Path
from typing import Optional, Type, List, Dict, Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright_stealth import Stealth


PAGE_LOAD_TIMEOUT: int = 60_000

_INIT_SCRIPT: str = """
try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
} catch (_) {}

try {
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
} catch (_) {}

try {
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
} catch (_) {}

try {
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
} catch (_) {}

try {
    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
} catch (_) {}

try {
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
} catch (_) {}

try {
    window.chrome = {
        runtime: { connect: () => {}, sendMessage: () => {} },
        devtools: {},
        loadTimes: () => {},
        csi: () => {},
        app: {},
    };
} catch (_) {}

try {
    const origQuery = Permissions.prototype.query;
    Permissions.prototype.query = function(desc) {
        if (desc.name === 'notifications') return Promise.resolve({ state: 'prompt' });
        return origQuery.call(this, desc);
    };
} catch (_) {}
"""


class BrowserManager:
    """Manages a Playwright browser instance with stealth protection."""

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._stealth: Stealth = Stealth()
        self._playwright_cm: Optional[Type[async_playwright]] = None

    @staticmethod
    def _random_viewport() -> dict:
        """Slightly random viewport to avoid fixed pattern detection."""
        w = random.randint(1900, 1940)
        h = random.randint(1040, 1100)
        return {"width": w, "height": h}

    @staticmethod
    def _build_args(extra: Optional[list[str]] = None) -> list[str]:
        args = [
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-sync",
            "--lang=en-US",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--allow-running-insecure-content",
            "--disable-client-side-phishing-detection",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-domain-reliability",
            "--disable-breakpad",
        ]
        if extra:
            args.extend(extra)
        return args

    async def _apply_init_scripts(self, ctx: BrowserContext) -> None:
        await ctx.add_init_script(_INIT_SCRIPT)
        await self._stealth.apply_stealth_async(ctx)

    async def launch(
        self,
        chromium_path: Optional[str] = None,
        headless: bool = False,
        user_data_dir: Optional[str] = None,
    ) -> Page:
        """Launch browser with stealth and return the main page."""
        if user_data_dir:
            return await self._launch_persistent(
                Path(user_data_dir), chromium_path, headless,
            )

        self._playwright_cm = self._stealth.use_async(async_playwright())
        self._playwright = await self._playwright_cm.__aenter__()

        launch_args: dict = {
            "headless": headless,
            "args": self._build_args(),
        }
        if chromium_path:
            launch_args["executable_path"] = chromium_path

        self._browser = await self._playwright.chromium.launch(**launch_args)
        vp = self._random_viewport()
        self._context = await self._browser.new_context(viewport=vp, screen=vp)
        await self._apply_init_scripts(self._context)
        self._page = await self._context.new_page()
        return self._page

    async def _launch_persistent(
        self,
        data_dir: Path,
        chromium_path: Optional[str],
        headless: bool,
    ) -> Page:
        """Launch a persistent browser context (full profile persistence)."""
        self._playwright = await async_playwright().start()
        vp = self._random_viewport()

        self._context = await self._playwright.chromium.launch_persistent_context(
            str(data_dir),
            headless=headless,
            args=self._build_args(),
            executable_path=chromium_path,
            viewport=vp,
            screen=vp,
        )

        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

        await self._apply_init_scripts(self._context)

        return self._page

    async def navigate(self, url: str, timeout: int = PAGE_LOAD_TIMEOUT) -> None:
        """Navigate the main page to the given URL."""
        if not self._page:
            raise RuntimeError("Browser not launched. Call launch() first.")
        await self._page.goto(url, timeout=timeout, wait_until="domcontentloaded")

    @staticmethod
    def _resolve_selector(selector: str) -> str:
        """Prefix with xpath= if the selector looks like an XPath expression."""
        if selector.startswith(("/", "./", "(")):
            return f"xpath={selector}"
        return selector

    async def fill_field(self, selector: str, value: str) -> None:
        """Fill a form field identified by a CSS or XPath selector."""
        if not self._page:
            raise RuntimeError("Browser not launched.")
        await self._page.fill(self._resolve_selector(selector), value)

    async def click(self, selector: str, force: bool = False) -> None:
        """Click an element identified by a CSS or XPath selector."""
        if not self._page:
            raise RuntimeError("Browser not launched.")
        await self._page.click(self._resolve_selector(selector), force=force)

    async def close(self) -> None:
        """Close all browser resources gracefully."""
        errors: list[str] = []

        if self._page:
            try:
                await self._page.close()
            except Exception as e:
                errors.append(f"page: {e}")
            finally:
                self._page = None

        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                errors.append(f"context: {e}")
            finally:
                self._context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                errors.append(f"browser: {e}")
            finally:
                self._browser = None

        if self._playwright_cm:
            try:
                await self._playwright_cm.__aexit__(None, None, None)
            except Exception as e:
                errors.append(f"playwright: {e}")
            finally:
                self._playwright_cm = None
                self._playwright = None

        elif self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                errors.append(f"playwright stop: {e}")
            finally:
                self._playwright = None

        real_errors = [e for e in errors if "has been closed" not in e]
        if real_errors:
            raise RuntimeError(
                f"Errors during cleanup: {'; '.join(real_errors)}"
            )

    async def get_cookies(self) -> List[Dict[str, Any]]:
        """Export all cookies from the current browser context."""
        if not self._context:
            raise RuntimeError("Browser not launched.")
        return await self._context.cookies()

    async def add_cookies(self, cookies: List[Dict[str, Any]]) -> None:
        """Import cookies into the current browser context."""
        if not self._context:
            raise RuntimeError("Browser not launched.")
        await self._context.add_cookies(cookies)

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Page not available.")
        return self._page

    @property
    def is_active(self) -> bool:
        return self._browser is not None and self._context is not None


_browser_manager_instance: BrowserManager = BrowserManager()


def get_browser_manager() -> BrowserManager:
    return _browser_manager_instance
