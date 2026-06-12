from playwright.async_api import Page

from utils.logger import log, Tags


CONTINUE_BTN: str = 'button[data-automation-id="card-button"]'
OTP_INPUT: str = 'input[data-automation-id="code"]'
SUBMIT_BTN: str = 'button[dataautomationid="card-button"]'


async def handle_mfa(page: Page) -> None:
    """Complete the Symantec VIP MFA flow: continue, ask for code, submit."""
    log("INFO", Tags.MFA, "MFA page detected, clicking CONTINUE ...")
    await page.click(CONTINUE_BTN, force=True)
    await page.wait_for_timeout(2000)

    log("INFO", Tags.MFA, "Waiting for OTP input field ...")
    await page.wait_for_selector(OTP_INPUT, timeout=15_000)

    code: str = input(f"\n{'='*60}\n  Enter the Symantec VIP code: ").strip()
    print(f"{'='*60}\n")

    log("INFO", Tags.MFA, "Filling OTP code ...")
    await page.fill(OTP_INPUT, code)

    await page.wait_for_selector(SUBMIT_BTN, timeout=5000)
    await page.click(SUBMIT_BTN, force=True)

    log("SUCCESS", Tags.MFA, "OTP submitted.")
