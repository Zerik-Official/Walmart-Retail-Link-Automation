from typing import Optional, Type, List, Dict, Any
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright
from playwright_stealth import Stealth


PAGE_LOAD_TIMEOUT: int = 30_000


class BrowserManager:
    """Manages a Playwright browser instance with stealth protection."""

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._stealth: Stealth = Stealth()
        self._playwright_cm: Optional[Type[async_playwright]] = None

    async def launch(
        self,
        chromium_path: Optional[str] = None,
        headless: bool = False,
        user_data_dir: Optional[str] = None,
    ) -> Page:
        """Launch browser with stealth and return the main page.

        If user_data_dir is provided, uses a persistent context so that
        cookies, localStorage, IndexedDB, etc. survive across runs.
        """
        if user_data_dir:
            return await self._launch_persistent(
                Path(user_data_dir), chromium_path, headless,
            )

        self._playwright_cm = self._stealth.use_async(async_playwright())
        self._playwright = await self._playwright_cm.__aenter__()

        launch_args: dict = {
            "headless": headless,
            "args": ["--start-maximized"],
        }
        if chromium_path:
            launch_args["executable_path"] = chromium_path

        self._browser = await self._playwright.chromium.launch(**launch_args)
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            screen={"width": 1920, "height": 1080},
        )
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

        self._context = await self._playwright.chromium.launch_persistent_context(
            str(data_dir),
            headless=headless,
            args=["--start-maximized"],
            executable_path=chromium_path,
            viewport={"width": 1920, "height": 1080},
            screen={"width": 1920, "height": 1080},
        )

        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()

        await self._stealth.apply_stealth_async(self._context)

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
            raise RuntimeError("Page not available. Call launch() first.")
        return self._page

    @property
    def is_active(self) -> bool:
        return self._browser is not None and self._context is not None


_browser_manager_instance: BrowserManager = BrowserManager()


def get_browser_manager() -> BrowserManager:
    """Return the global singleton BrowserManager instance."""
    return _browser_manager_instance
