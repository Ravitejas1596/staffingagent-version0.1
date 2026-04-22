"""Capture Command Center demo screenshots for the marketing site.

Uses the static demo at ``site/command-center/index.html`` as the source of
truth (it's a faithful mirror of the React Command Center). Runs Playwright
against a local HTTP server rooted at ``site/`` so absolute asset paths
(``/chat-widget.js`` etc.) resolve the same way they do in production.

Usage:
    # one-time environment setup
    python3 -m venv .venv-capture
    .venv-capture/bin/pip install playwright
    .venv-capture/bin/python -m playwright install chromium

    # regenerate all screenshots (PNG + WebP) in site/images/cc/
    .venv-capture/bin/python scripts/capture_site_screenshots.py

The six frames captured are documented in ``site/images/cc/README.md``.
"""

from __future__ import annotations

import http.server
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
from contextlib import closing
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
OUT_DIR = SITE_DIR / "images" / "cc"

VIEWPORT = {"width": 1440, "height": 900}
DEVICE_SCALE_FACTOR = 2  # retina

# Cards used for WebP conversion quality. cwebp -q 82 ≈ visually lossless for UI.
WEBP_QUALITY = "82"


def _find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return  # silence default access log


def _start_server(port: int) -> socketserver.TCPServer:
    handler = lambda *a, **kw: _QuietHandler(*a, directory=str(SITE_DIR), **kw)  # noqa: E731
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _wait_for_demo(page: Page) -> None:
    """Wait for the demo's cockpit view to be fully rendered."""
    page.wait_for_selector("#commandCenterView.active", timeout=10_000)
    page.wait_for_selector(".cc-cockpit", timeout=10_000)
    # Give inline JS (mock renders, agent fleet) a beat to paint.
    page.wait_for_timeout(600)


def _capture(page: Page, out_png: Path, *, clip: dict | None = None, full_page: bool = False) -> None:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out_png), clip=clip, full_page=full_page, type="png", scale="device")


def _bounding_box(page: Page, selector: str) -> dict:
    box = page.locator(selector).bounding_box()
    if not box:
        raise RuntimeError(f"Could not resolve bounding box for {selector!r}")
    # Pad a little so nothing is clipped on the edges.
    pad = 12
    return {
        "x": max(0, box["x"] - pad),
        "y": max(0, box["y"] - pad),
        "width": box["width"] + pad * 2,
        "height": box["height"] + pad * 2,
    }


def _convert_to_webp(png_path: Path) -> Path | None:
    """Convert a PNG to WebP next to it. Returns the WebP path or None."""
    if shutil.which("cwebp") is None:
        print("  ! cwebp not found on PATH; skipping WebP conversion")
        return None
    webp_path = png_path.with_suffix(".webp")
    result = subprocess.run(
        ["cwebp", "-q", WEBP_QUALITY, "-mt", "-quiet", str(png_path), "-o", str(webp_path)],
        check=False,
    )
    if result.returncode != 0:
        print(f"  ! cwebp failed for {png_path.name}")
        return None
    return webp_path


def _size_kb(path: Path) -> str:
    return f"{path.stat().st_size / 1024:.1f} KB"


def capture_cockpit_hero(page: Page) -> None:
    print("• cockpit-hero.png")
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(200)
    out = OUT_DIR / "cockpit-hero.png"
    # Full visible viewport of the cockpit landing.
    _capture(page, out, clip={"x": 0, "y": 0, "width": VIEWPORT["width"], "height": VIEWPORT["height"]})
    _finalize(out)


def capture_agent_fleet(page: Page) -> None:
    print("• agent-fleet.png")
    # The Agent Fleet panel is a `.cc-panel` whose header title contains "Agent Fleet".
    fleet_selector = ".cc-panel:has(.cc-fleet)"
    page.evaluate(
        "(function(){var p=document.querySelector(%r);if(p){p.scrollIntoView({block:'center'});}})()"
        % fleet_selector
    )
    page.wait_for_timeout(250)
    clip = _bounding_box(page, fleet_selector)
    out = OUT_DIR / "agent-fleet.png"
    _capture(page, out, clip=clip)
    _finalize(out)


def capture_alert_queue(page: Page) -> None:
    print("• alert-queue.png")
    page.evaluate("showAlertQueueView()")
    page.wait_for_selector("#alertQueueView.active", timeout=5_000)
    page.wait_for_selector(".aq-page", timeout=5_000)
    page.wait_for_timeout(400)
    out = OUT_DIR / "alert-queue.png"
    _capture(page, out, clip={"x": 0, "y": 0, "width": VIEWPORT["width"], "height": VIEWPORT["height"]})
    _finalize(out)


def capture_alert_queue_drawer(page: Page) -> None:
    print("• alert-queue-drawer.png")
    # Get the first alert id from the mock table to open a realistic drawer.
    alert_id = page.evaluate(
        "(function(){var r=document.querySelector('#aqTableBody tr[onclick]');"
        "if(!r)return null;var m=/aqOpenDrawer\\('([^']+)'\\)/.exec(r.getAttribute('onclick')||'');"
        "return m?m[1]:null;})()"
    )
    if not alert_id:
        raise RuntimeError("Could not find an alert row to open")
    page.evaluate(f"aqOpenDrawer('{alert_id}')")
    page.wait_for_selector("#aqDrawer.open", timeout=5_000)
    page.wait_for_timeout(400)
    out = OUT_DIR / "alert-queue-drawer.png"
    _capture(page, out, clip={"x": 0, "y": 0, "width": VIEWPORT["width"], "height": VIEWPORT["height"]})
    _finalize(out)


def capture_vms_match_review(page: Page) -> None:
    print("• vms-match-review.png")
    # Close drawer first
    page.evaluate("(function(){try{aqCloseDrawer()}catch(e){}})()")
    page.wait_for_timeout(150)
    page.evaluate("showVmsReconciliationView()")
    page.wait_for_selector("#vmsReconciliationView.active", timeout=5_000)
    page.wait_for_selector("#vmrRows .vmr-row", timeout=5_000)
    page.wait_for_timeout(300)
    # Expand the first pending match row for the rich side-by-side VMS↔Bullhorn compare.
    page.evaluate(
        "(function(){var first=document.querySelector('#vmrRows .vmr-row');"
        "if(!first)return;var summary=first.querySelector('.vmr-row-summary');"
        "if(summary){summary.click();}})()"
    )
    page.wait_for_timeout(350)
    out = OUT_DIR / "vms-match-review.png"
    # The expanded row can push the page long; capture a tall viewport-anchored crop.
    _capture(page, out, full_page=False, clip={"x": 0, "y": 0, "width": VIEWPORT["width"], "height": VIEWPORT["height"]})
    _finalize(out)


def capture_agent_plan(page: Page) -> None:
    print("• agent-plan.png")
    # Make sure we're back on the cockpit before opening the modal.
    page.evaluate("showCommandCenter()")
    page.wait_for_selector("#commandCenterView.active", timeout=5_000)
    page.wait_for_timeout(200)
    page.evaluate("apvOpen('time-anomaly')")
    page.wait_for_selector(".apv-modal", timeout=5_000)
    # Drive it into plan_ready phase so the checklist + summary stats render.
    page.evaluate(
        "(function(){if(typeof apvStartPlan==='function'){apvStartPlan();}})()"
    )
    # Planning animation is ~4x 900ms steps; wait for the plan_ready phase to become visible.
    page.wait_for_function(
        "(function(){var el=document.querySelector('#apvPhasePlanReady, [data-phase=\"plan_ready\"]');"
        "if(el){var r=el.getBoundingClientRect();return r.width>0 && r.height>0;}"
        "var lbl=document.querySelector('.apv-phase-label.plan_ready');"
        "if(lbl){var rr=lbl.getBoundingClientRect();return rr.width>0 && rr.height>0;}"
        "return false;})()",
        timeout=8_000,
    )
    page.wait_for_timeout(300)
    out = OUT_DIR / "agent-plan.png"
    _capture(page, out, clip={"x": 0, "y": 0, "width": VIEWPORT["width"], "height": VIEWPORT["height"]})
    _finalize(out)


def _finalize(png_path: Path) -> None:
    webp = _convert_to_webp(png_path)
    png_size = _size_kb(png_path)
    if webp is not None:
        print(f"    PNG {png_size}  →  WebP {_size_kb(webp)}")
    else:
        print(f"    PNG {png_size}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    port = _find_free_port()
    httpd = _start_server(port)
    base_url = f"http://127.0.0.1:{port}"
    print(f"▸ Serving {SITE_DIR} at {base_url}")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            context = browser.new_context(
                viewport=VIEWPORT,
                device_scale_factor=DEVICE_SCALE_FACTOR,
            )
            # Hide both chat widgets (sales bubble + in-app demo assistant) so marketing
            # screenshots stay focused on the product UI itself.
            context.add_init_script(
                "var s=document.createElement('style');"
                "s.textContent='#sa-chat-bubble,#sa-chat-panel,#sa-chat-tooltip,"
                ".cw-bubble,#cwBubble,.cw-panel,#cwPanel{display:none !important;}';"
                "(document.head||document.documentElement).appendChild(s);"
            )
            page = context.new_page()
            page.goto(f"{base_url}/command-center/", wait_until="networkidle")
            _wait_for_demo(page)
            # Belt-and-suspenders: hide chat widgets after page scripts run.
            page.add_style_tag(
                content=(
                    "#sa-chat-bubble,#sa-chat-panel,#sa-chat-tooltip,"
                    ".cw-bubble,#cwBubble,.cw-panel,#cwPanel"
                    "{display:none !important;visibility:hidden !important;}"
                )
            )
            page.evaluate(
                "['sa-chat-bubble','sa-chat-panel','sa-chat-tooltip','cwBubble','cwPanel']"
                ".forEach(function(id){var e=document.getElementById(id);"
                "if(e){e.style.setProperty('display','none','important');e.remove();}});"
            )

            capture_cockpit_hero(page)
            capture_agent_fleet(page)
            capture_alert_queue(page)
            capture_alert_queue_drawer(page)
            capture_vms_match_review(page)
            capture_agent_plan(page)

            browser.close()
    finally:
        httpd.shutdown()

    print(f"✓ Wrote screenshots to {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
