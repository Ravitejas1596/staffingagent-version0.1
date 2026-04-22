# Command Center marketing screenshots

These screenshots power the marketing pages under `site/` (homepage, the-command-center, per-agent). They are captured from the static Command Center demo at `site/command-center/index.html` — a faithful mirror of the production React app that runs deterministically in a headless browser.

Every frame ships as **both a PNG (master) and WebP (served)** at 2× (retina). Mark-up references WebP with a PNG fallback via `<picture>`.

## Frames

| File | What it shows |
|---|---|
| `cockpit-hero.{png,webp}` | Cockpit landing: top nav, "Command Center · LIVE" title, 6 KPI tiles, Action Queue preview |
| `agent-fleet.{png,webp}` | Agent Fleet panel (4 Active, 1 Beta, 2 Coming Soon), tight crop |
| `alert-queue.{png,webp}` | Alert Queue table with KPI row, state filter pills, severity filter, reversal-window footer |
| `alert-queue-drawer.{png,webp}` | Alert Queue with the resolve drawer open — candidate/context/timeline/resolution UI |
| `vms-match-review.{png,webp}` | VMSMatchReview with a row expanded, side-by-side VMS↔Bullhorn compare and AI reasoning pill |
| `agent-plan.{png,webp}` | AgentPlanView modal in `plan_ready` phase — summary stats, checkbox action list, Approve & Execute footer |

## Regenerating

One command, from the repo root:

```bash
python3 -m venv .venv-capture
.venv-capture/bin/pip install playwright
.venv-capture/bin/python -m playwright install chromium
.venv-capture/bin/python scripts/capture_site_screenshots.py
```

The script:
- Spins up a local HTTP server rooted at `site/` (on a free port) so absolute asset paths like `/chat-widget.js` resolve the way they do in production.
- Navigates to `/command-center/` at viewport **1440×900 @ 2×**.
- Hides the marketing sales-chat bubble *and* the in-app demo assistant widget so the screenshots stay focused on the product UI.
- Triggers the relevant in-page actions to reach the right state for each frame (open drawer, expand VMR row, run agent planning animation to `plan_ready`).
- Writes PNGs, then converts to WebP via `cwebp -q 82 -mt` (requires `cwebp` on `PATH`; install via `brew install webp`).

## When to regenerate

Re-run the script any time the demo at `site/command-center/index.html` changes in a way that would visibly affect one of the six frames — new KPI, changed copy, layout shift, etc. These screenshots do not auto-update; if the demo diverges silently the marketing pages will silently go stale.

## Budget

Targets (after WebP conversion):
- Hero frame: ≤ 180 KB
- Panel crops (agent fleet): ≤ 80 KB
- Full-viewport frames (queue, drawer, VMR, plan): ≤ 170 KB

Current sizes are well under these targets. If a frame exceeds its budget, re-run with `-q 75` on cwebp or crop tighter.
