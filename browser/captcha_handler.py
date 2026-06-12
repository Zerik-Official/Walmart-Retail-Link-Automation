import asyncio
import random
import math
from typing import Optional, Dict, Any

from playwright.async_api import Page

from utils.logger import log, Tags


PX_EVALUATION_TIMEOUT: int = 60_000
PX_RESOLVE_TIMEOUT: int = 120_000
HOLD_MIN: float = 1.8
HOLD_MAX: float = 4.5

LOGIN_BTN: str = 'button[data-automation-id="loginBtn"]'

# Signals that indicate a PX challenge is present on the page
_PX_CHALLENGE_SIGNALS: list[str] = [
    "px-captcha",
    "px-challenge",
    "px-loader",
    "custom-iframe",
    "_pxCaptcha",
    "perimeterx",
]


async def _wait_for_button_enabled(page: Page, timeout: int = PX_EVALUATION_TIMEOUT) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < deadline:
        try:
            el = await page.query_selector(LOGIN_BTN)
            if el and await el.get_attribute("disabled") is None:
                await asyncio.sleep(1)
                return True
        except Exception:
            pass
        await asyncio.sleep(0.3)
    return False


async def _detect_px_challenge(page: Page) -> bool:
    """Check whether PX is present on the page."""
    for signal in _PX_CHALLENGE_SIGNALS:
        found = await page.evaluate(
            f"document.querySelector('[data-px-captcha]') !== null || "
            f"document.querySelector('custom-iframe') !== null || "
            f"document.getElementById('px-captcha') !== null || "
            f"document.querySelector('meta[content*=\"{signal}\"]') !== null || "
            f"document.querySelector('iframe[src*=\"{signal}\"]') !== null || "
            f"(window.___px___ && window.___px___.isCaptcha)"
        )
        if found:
            return True
    return False


async def _find_hold_target(page: Page) -> Optional[Dict[str, float]]:
    """Search the DOM (including Shadow DOM and custom-iframes) for the PX hold button."""
    result: Optional[Dict[str, Any]] = await page.evaluate(
        """
        () => {
            const pxKeywords = [
                'press', 'hold', 'mantener', 'presionado', 'pulsar',
                'human challenge', 'verificación', 'verification',
                'challenge', 'appuyer', 'tartsd',
            ];

            function getRect(el) {
                const r = el.getBoundingClientRect();
                return (r.width > 0 && r.height > 0)
                    ? { x: r.x, y: r.y, w: r.width, h: r.height }
                    : null;
            }

            function scanText(root) {
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
                let node;
                while (node = walker.nextNode()) {
                    const text = (node.textContent || '').trim().toLowerCase();
                    const matchCount = pxKeywords.filter(k => text.includes(k)).length;
                    if (matchCount >= 2) {
                        const rect = getRect(node);
                        if (rect) return rect;
                    }
                }
                return null;
            }

            // 1. Look into custom-iframes and their shadow roots
            const customs = document.querySelectorAll('custom-iframe');
            for (const c of customs) {
                if (c.shadowRoot) {
                    const r = scanText(c.shadowRoot);
                    if (r) return r;
                }
            }

            // 2. Look into PX iframes
            const iframes = document.querySelectorAll('iframe');
            for (const f of iframes) {
                try {
                    const doc = f.contentDocument || f.contentWindow.document;
                    if (doc) {
                        const r = scanText(doc);
                        if (r) return r;
                    }
                } catch (_) {}
            }

            // 3. Scan shadow roots across the whole page
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.shadowRoot) {
                    const r = scanText(el.shadowRoot);
                    if (r) return r;
                }
            }

            // 4. Fallback: scan text in the main document
            const r = scanText(document);
            if (r) return r;

            // 5. Last resort: look for a PX loader element
            const loader = document.querySelector('.px-loader, .px-loader-wrapper, [class*="px-load"]');
            if (loader) return getRect(loader);

            return null;
        }
        """
    )

    if result:
        log("DEBUG", Tags.PX, f"Hold target found at ({result['x']:.0f}, {result['y']:.0f}) size ({result['w']:.0f}x{result['h']:.0f})")
    return result


async def _micro_movements(page: Page, x: float, y: float, duration: float) -> None:
    """Simulate tiny mouse jitter during hold, mimicking real human behavior."""
    steps = random.randint(int(duration * 3), int(duration * 6))
    interval = duration / steps
    for _ in range(steps):
        jitter_x = random.uniform(-1.5, 1.5)
        jitter_y = random.uniform(-1.5, 1.5)
        await page.mouse.move(x + jitter_x, y + jitter_y, steps=1)
        await asyncio.sleep(interval * random.uniform(0.6, 1.4))


async def _mouse_hold(page: Page, x: float, y: float) -> bool:
    """Press and hold with realistic micro-movements, then release."""
    try:
        duration = random.uniform(HOLD_MIN, HOLD_MAX)
        log("INFO", Tags.PX, f"Holding at ({x:.0f}, {y:.0f}) for {duration:.1f}s ...")

        steps = random.randint(5, 12)
        for i in range(1, steps + 1):
            cx = x + math.sin(i / steps * math.pi) * random.uniform(-3, 3)
            cy = y + math.cos(i / steps * math.pi) * random.uniform(-3, 3)
            await page.mouse.move(cx, cy, steps=2)
            await asyncio.sleep(0.02 * random.uniform(0.5, 1.5))

        await page.mouse.down()
        await asyncio.sleep(0.05)

        await _micro_movements(page, x, y, duration)

        await page.mouse.up()
        await asyncio.sleep(0.1)

        await page.mouse.move(x + random.uniform(10, 40), y + random.uniform(5, 20), steps=5)

        await asyncio.sleep(2)
        return await _wait_for_button_enabled(page, timeout=5_000)

    except Exception as e:
        log("DEBUG", Tags.PX, f"Mouse hold failed: {e}")
        return False


async def _inspect_px_window(page: Page) -> None:
    """Dump all PX-related properties exposed on window."""
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

            const frames = document.querySelectorAll('iframe, custom-iframe');
            const pxFrames = [];
            for (const f of frames) {
                const src = f.getAttribute('src') || '';
                const title = f.getAttribute('title') || '';
                const id = f.id || '';
                const cls = f.className || '';
                if (/px|perimeter|captcha/i.test(src + title + id + cls)) {
                    pxFrames.push({ tag: f.tagName, src: src.slice(0, 150), title, id, visible: f.offsetParent !== null });
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


async def handle_px_challenge(page: Page) -> bool:
    """Detect and attempt to solve the PX Press & Hold challenge."""
    log("INFO", Tags.PX, "Waiting for PX evaluation ...")

    if await _wait_for_button_enabled(page):
        log("SUCCESS", Tags.PX, "PX passed without challenge.")
        return True

    log("INFO", Tags.PX, "Button still disabled, inspecting PX internals ...")
    await asyncio.sleep(2)
    await _inspect_px_window(page)

    has_px = await _detect_px_challenge(page)
    log("INFO", Tags.PX, f"PX challenge detected in DOM: {has_px}")

    log("INFO", Tags.PX, "Searching for hold target ...")
    await asyncio.sleep(1)

    for attempt in range(1, 4):
        log("INFO", Tags.PX, f"Hold attempt {attempt}/3 ...")

        target = await _find_hold_target(page)
        if target:
            cx = target["x"] + target["w"] / 2
            cy = target["y"] + target["h"] / 2
            if await _mouse_hold(page, cx, cy):
                log("SUCCESS", Tags.PX, "Challenge solved via hold target.")
                return True
        else:
            log("INFO", Tags.PX, "Hold target not found by text, trying viewport center ...")
            vp = page.viewport_size
            if vp and await _mouse_hold(page, vp["width"] / 2, vp["height"] / 2):
                log("SUCCESS", Tags.PX, "Challenge solved via viewport center hold.")
                return True

        if attempt < 3:
            wait = random.uniform(3, 8)
            log("INFO", Tags.PX, f"Retrying in {wait:.0f}s ...")
            await asyncio.sleep(wait)

    log("WARNING", Tags.PX, "Could not solve PX challenge after 3 attempts.")
    await _find_any_visible_text(page)
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
