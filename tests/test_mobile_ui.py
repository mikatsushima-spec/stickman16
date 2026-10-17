from pathlib import Path
from playwright.sync_api import sync_playwright
import json, os, time

URL = os.getenv("GAME_URL", "http://127.0.0.1:8765/")
OUT = Path("test-results")
OUT.mkdir(exist_ok=True)
report = {"url": URL, "checks": [], "console_errors": [], "page_errors": []}

def check(name, fn):
    try:
        fn()
        report["checks"].append({"name": name, "status": "passed"})
    except Exception as exc:
        report["checks"].append({"name": name, "status": "failed", "error": str(exc)})
        raise

def drag(page, x1, y1, x2, y2, steps=15):
    page.mouse.move(x1, y1)
    page.mouse.down()
    for i in range(1, steps + 1):
        page.mouse.move(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
        page.wait_for_timeout(15)
    page.mouse.up()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader"
    ])
    context = browser.new_context(viewport={"width": 393, "height": 852}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.on("console", lambda m: report["console_errors"].append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: report["page_errors"].append(str(e)))
    try:
        check("page loads", lambda: page.goto(URL, wait_until="domcontentloaded", timeout=60000))
        page.wait_for_timeout(4500)
        check("loading overlay disappears", lambda: page.locator("#loading").wait_for(state="detached", timeout=20000))
        page.screenshot(path=str(OUT / "01-start-screen.png"), full_page=True)
        check("3D renderer initialized", lambda: page.locator("#game canvas").wait_for(timeout=20000))
        check("PLAY starts game", lambda: (page.locator("#start").click(), page.locator("#menu").wait_for(state="hidden", timeout=5000)))
        page.screenshot(path=str(OUT / "02-gameplay.png"), full_page=True)
        initial = page.locator("#clock").inner_text()
        page.wait_for_timeout(1300)
        assert page.locator("#clock").inner_text() != initial, "Timer did not advance"
        report["checks"].append({"name": "timer advances", "status": "passed"})
        # A visual delta proves the scene actually responds, not merely that pointer events were sent.
        before_swipe = page.locator("#game canvas").screenshot()
        check("swipe controls", lambda: drag(page, 260, 440, 120, 490))
        page.wait_for_timeout(300)
        after_swipe = page.locator("#game canvas").screenshot()
        assert before_swipe != after_swipe, "Swipe did not change rendered scene"
        report["checks"].append({"name":"swipe changes 3D scene","status":"passed"})
        page.screenshot(path=str(OUT / "03-after-swipe.png"), full_page=True)
        # Hold the virtual joystick to test sustained motion.
        before_joy = page.locator("#game canvas").screenshot()
        page.mouse.move(65, 775)
        page.mouse.down()
        page.mouse.move(90, 745, steps=8)
        page.wait_for_timeout(900)
        page.mouse.up()
        after_joy = page.locator("#game canvas").screenshot()
        assert before_joy != after_joy, "Joystick did not move camera"
        report["checks"].append({"name":"joystick moves camera","status":"passed"})
        check("fire button", lambda: page.locator("#fire").click())
        assert page.locator("#notice").inner_text() in ("MISS — もう少し狙って！","HIT! +1"), "Fire did not invoke shooting logic"
        report["checks"].append({"name":"fire produces shot result","status":"passed"})
        check("radar activates", lambda: (page.locator("#radar").click(), page.locator("#radarCanvas").wait_for(state="visible", timeout=2000)))
        page.screenshot(path=str(OUT / "04-radar.png"), full_page=True)
        assert not report["page_errors"], "JavaScript errors: " + "; ".join(report["page_errors"])
        assert not report["console_errors"], "Console errors: " + "; ".join(report["console_errors"])
        report["checks"].append({"name": "no uncaught JavaScript errors", "status": "passed"})
    except Exception as exc:
        report["fatal_error"] = str(exc)
        page.screenshot(path=str(OUT / "error-state.png"), full_page=True)
    finally:
        (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        browser.close()
if "fatal_error" in report:
    raise SystemExit("UI smoke test failed: " + report["fatal_error"])
print(json.dumps(report, ensure_ascii=False, indent=2))
