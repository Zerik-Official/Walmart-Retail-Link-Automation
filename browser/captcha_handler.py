import asyncio
from typing import Optional, Dict, Any

from playwright.async_api import Page

from utils.logger import log, Tags


PX_EVALUATION_TIMEOUT: int = 40_000
PX_RESOLVE_TIMEOUT: int = 120_000
HOLD_DURATION: float = 6.0

LOGIN_BTN: str = 'button[data-automation-id="loginBtn"]'


async def _wait_for_button_enabled(page: Page, timeout: int = PX_EVALUATION_TIMEOUT) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < deadline:
        try:
            el = await page.query_selector(LOGIN_BTN)
            if el and await el.get_attribute("disabled") is None:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


async def _find_hold_target(page: Page) -> Optional[Dict[str, float]]:
    """
    Scan the entire DOM (including shadow roots) for the Press & Hold
    button. Returns {x, y, w, h} of the best candidate, or None.
    """
    result: Optional[Dict[str, Any]] = await page.evaluate(
        """
        () => {
            function getClientRect(el) {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0
                    ? { x: r.x, y: r.y, w: r.width, h: r.height }
                    : null;
            }

            function scan(root) {
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                let node;
                while (node = walker.nextNode()) {
                    const text = (node.textContent || '').trim().toLowerCase();
                    if (text.includes('press') && text.includes('hold')) {
                        const rect = getClientRect(node);
                        if (rect) return rect;
                    }
                }
                return null;
            }

            let r = scan(document);
            if (r) return r;

            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.shadowRoot) {
                    r = scan(el.shadowRoot);
                    if (r) return r;
                }
            }
            return null;
        }
        """
    )

    if result:
        log("DEBUG", Tags.PX, f"Hold target found at ({result['x']:.0f}, {result['y']:.0f})")
    return result


async def _find_any_visible_text(page: Page) -> None:
    """Debug helper: log visible text on the page."""
    texts = await page.evaluate(
        """
        () => {
            const els = document.querySelectorAll('p, span, div, button, h1, h2, h3, h4');
            const out = [];
            for (const el of els) {
                const t = (el.textContent || '').trim();
                if (t.length > 3 && t.length < 200) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) out.push(t.slice(0, 120));
                }
            }
            return out;
        }
        """
    )
    if texts:
        log("DEBUG", Tags.PX, f"Visible text on page ({len(texts)} elements):")
        for t in texts[:30]:
            log("DEBUG", Tags.PX, f"  -> {t}")


async def _mouse_hold(page: Page, x: float, y: float) -> bool:
    """Press and hold the mouse at (x, y), then release."""
    try:
        log("INFO", Tags.PX, f"Holding at ({x:.0f}, {y:.0f}) for {HOLD_DURATION}s ...")
        await page.mouse.move(x, y)
        await page.mouse.down()
        await asyncio.sleep(HOLD_DURATION)
        await page.mouse.up()

        await asyncio.sleep(2)
        return await _wait_for_button_enabled(page, timeout=5_000)
    except Exception as e:
        log("DEBUG", Tags.PX, f"Mouse hold failed: {e}")
        return False


async def _inspect_px_window(page: Page) -> None:
    """Dump all PX-related properties exposed on window, including object internals."""
    info: Dict[str, Any] = await page.evaluate(
        """
        () => {
            const out = {};
            const keywords = ['px', 'perimeterx', 'captcha', '_px', 'PX', '_pxCaptcha'];

            function describe(val) {
                if (typeof val === 'function') return `fn(${val.length} args)`;
                if (typeof val === 'object' && val !== null) {
                    const keys = Object.keys(val);
                    const details = {};
                    for (const k of keys.slice(0, 10)) {
                        const v = val[k];
                        details[k] = typeof v === 'function'
                            ? `fn(${v.length} args)`
                            : typeof v === 'object' && v !== null
                                ? `obj(${Object.keys(v).length} keys)`
                                : String(v).slice(0, 100);
                    }
                    return `obj(${keys.length} keys): ${JSON.stringify(details)}`;
                }
                return String(val).slice(0, 200);
            }

            for (const key of Object.getOwnPropertyNames(window)) {
                const lower = key.toLowerCase();
                if (keywords.some(k => lower.includes(k.toLowerCase()))) {
                    out[key] = describe(window[key]);
                }
            }

            const frames = document.querySelectorAll('iframe');
            const pxFrames = [];
            for (const f of frames) {
                const src = f.getAttribute('src') || '';
                const title = f.getAttribute('title') || '';
                if (src.toLowerCase().includes('px') || title.toLowerCase().includes('px') || title.toLowerCase().includes('captcha')) {
                    pxFrames.push({ src: src.slice(0, 150), title, visible: f.offsetParent !== null });
                }
            }
            out['__pxFrames__'] = pxFrames;

            return out;
        }
        """
    )
    for key, val in info.items():
        if isinstance(val, str) and len(val) > 300:
            log("DEBUG", Tags.PX, f"  window.{key} = {val[:300]}...")
        else:
            log("DEBUG", Tags.PX, f"  window.{key} = {val}")


async def handle_px_challenge(page: Page) -> bool:
    """Detect and attempt to solve the PX Press & Hold challenge."""
    log("INFO", Tags.PX, "Waiting for PX evaluation ...")

    if await _wait_for_button_enabled(page):
        log("SUCCESS", Tags.PX, "PX passed without challenge.")
        return True

    log("INFO", Tags.PX, "Button still disabled, inspecting PX internals ...")
    await asyncio.sleep(2)
    await _inspect_px_window(page)

    log("INFO", Tags.PX, "Searching DOM for 'Press & Hold' ...")
    await asyncio.sleep(1)

    target = await _find_hold_target(page)
    if target:
        cx = target["x"] + target["w"] / 2
        cy = target["y"] + target["h"] / 2
        if await _mouse_hold(page, cx, cy):
            log("SUCCESS", Tags.PX, "Challenge solved via Press & Hold element.")
            return True
    else:
        log("INFO", Tags.PX, "Press & Hold not found in DOM, dumping page text ...")
        await _find_any_visible_text(page)

        log("INFO", Tags.PX, "Trying viewport center as fallback ...")
        vp = page.viewport_size
        if vp and await _mouse_hold(page, vp["width"] / 2, vp["height"] / 2):
            log("SUCCESS", Tags.PX, "Challenge solved via viewport center hold.")
            return True

    log("WARNING", Tags.PX, "Could not solve PX challenge.")
    return False


async def wait_for_px_challenge_resolved(page: Page, timeout: int = PX_RESOLVE_TIMEOUT) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < deadline:
        try:
            if "/login" not in page.url:
                return True
            el = await page.query_selector(LOGIN_BTN)
            if el and await el.get_attribute("disabled") is None:
                return True
        except Exception:
            pass
        await asyncio.sleep(1)
    log("WARNING", Tags.PX, "Timed out waiting for PX resolution.")
    return False
