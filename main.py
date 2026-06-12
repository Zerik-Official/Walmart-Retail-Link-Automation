import asyncio
import sys

from config.settings import settings
from browser.manager import get_browser_manager
from browser.cookie_manager import load_cookies, save_cookies
from browser.captcha_handler import handle_px_challenge, wait_for_px_challenge_resolved
from browser.mfa_handler import handle_mfa
from libs.credential_resolver import resolve_credentials
from utils.logger import log, Tags
from utils.info import BANNER


USERNAME_SEL: str = 'input[data-automation-id="uname"]'
PASSWORD_SEL: str = 'input[data-automation-id="pwd"]'
LOGIN_BTN: str = 'button[data-automation-id="loginBtn"]'


async def _wait_for_url_contains(page, substring: str, timeout: int = 30_000) -> bool:
    try:
        await page.wait_for_url(f"**{substring}**", timeout=timeout)
        return True
    except Exception:
        return False


async def _do_full_login(page, manager, username: str, password: str) -> None:
    """Fill credentials, submit, handle PX and MFA."""
    log("INFO", Tags.LOGIN, "Filling username ...")
    await manager.fill_field(USERNAME_SEL, username)

    log("INFO", Tags.LOGIN, "Filling password ...")
    await manager.fill_field(PASSWORD_SEL, password)

    log("INFO", Tags.LOGIN, "Clicking login button ...")
    await manager.click(LOGIN_BTN, force=True)

    log("INFO", Tags.PX, "Checking for PerimeterX challenge ...")
    await handle_px_challenge(page)
    await wait_for_px_challenge_resolved(page)

    log("INFO", Tags.LOGIN, "Waiting for post-login redirect ...")
    on_mfa = await _wait_for_url_contains(page, "/mfa", timeout=40_000)

    if on_mfa:
        await handle_mfa(page)

    await page.wait_for_timeout(3000)
    await save_cookies(manager)


async def perform_login() -> None:
    """Orchestrate the full login flow."""
    settings.validate()

    creds = resolve_credentials(
        use_lastpass=settings.use_lastpass,
        walmart_username=settings.walmart_username,
        walmart_password=settings.walmart_password,
        lastpass_email=settings.lastpass_email,
        lastpass_password=settings.lastpass_password,
    )

    manager = get_browser_manager()
    page = await manager.launch(
        chromium_path=settings.chromium_path,
        headless=settings.headless,
        user_data_dir=settings.user_data_dir,
    )

    try:
        cookies_loaded = await load_cookies(manager)

        log("INFO", Tags.LOGIN, "Warming up at youtube.com ...")
        await manager.navigate("https://www.youtube.com")
        await page.wait_for_timeout(4000)

        log("INFO", Tags.LOGIN, f"Navigating to {settings.login_url} ...")
        await manager.navigate(settings.login_url)

        redirected = await _wait_for_url_contains(page, "/mfa", timeout=8_000)
        if not redirected:
            redirected = await _wait_for_url_contains(
                page, "supplier.wal-mart.com", timeout=5_000,
            )

        if redirected:
            log("SUCCESS", Tags.LOGIN, "Session valid, already past login.")
            if "/mfa" in page.url:
                await handle_mfa(page)
                await page.wait_for_timeout(3000)
                await save_cookies(manager)
        else:
            if cookies_loaded:
                log("INFO", Tags.LOGIN, "Cookies expired, performing full login.")
            await _do_full_login(page, manager, creds.username, creds.password)

        log("SUCCESS", Tags.MAIN, f"Final URL: {page.url}")
        log("INFO", Tags.MAIN, "Waiting for further instructions ...")
        input("\n  Press Enter to close the browser and exit ...")

    finally:
        await manager.close()


def main() -> None:
    print(BANNER)
    try:
        asyncio.run(perform_login())
    except KeyboardInterrupt:
        log("INFO", Tags.SYSTEM, "Interrupted by user.")
        sys.exit(0)
    except Exception as e:
        log("CRITICAL", Tags.SYSTEM, str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
