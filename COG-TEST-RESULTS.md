# P1 — cog / WebKit render + memory test on the dorm Pi 4

Run: 2026-08-11, over SSH against the live dorm Pi (Raspberry Pi 4 Model B Rev 1.5, 2GB).
Two passes: an initial test that found a rendering bug, then a **re-test after fixing it at true
1920×1080**. The live display was never interrupted (verified, §8).

## 1. Browser used

| | |
|---|---|
| Browser | **cog 0.18.4** (the real target, no fallback needed) |
| Engine | **WPE WebKit 2.48.3** |
| Packages added | `xvfb`, `x11-utils`, `imagemagick`, `cog`, `grim`, `libwpebackend-fdo-1.0-1` |
| Packages removed/changed | **none** (additive only, no upgrades, no reboot) |

Setup findings worth keeping for the product build:

- **`cog` has no X11 backend** on Debian 13 — only `drm`, `headless`, `wl`. Xvfb cannot drive it.
  I ran a second headless **wlroots** compositor (`labwc`, `WLR_BACKENDS=headless`) on its own
  socket `wayland-1`; the TV's compositor is `wayland-0` and was never touched.
- **`libwpebackend-fdo` is required** and is *not* pulled in by the `cog` package. Without it cog
  aborts: `libWPEBackend-default.so: cannot open shared object file`.
- `cog` has **no `--fullscreen` flag**; use `COG_PLATFORM_WL_VIEW_FULLSCREEN=1`. Without it cog
  opens a small window and any memory figure is not a real 1080p measurement.

## 2. Peak memory — at TRUE 1920×1080

Verified full-frame (content bounding box measured at 1920×1078 of a 1920×1080 output):

| Process | RSS |
|---|---|
| `cog` (UI) | 105 MB |
| `WPEWebProcess` (renderer) | 184 MB |
| `WPENetworkProcess` | 68 MB |
| **Total** | **355 MB** |

Notably, memory barely moved between 720p (357 MB) and 1080p (355 MB) — this workload is
DOM/JS-bound, not framebuffer-bound. That is a good sign for a cheap board.

## 3. 400MB cap

**Survived, at true 1080p.** `systemd-run --user --scope -p MemoryMax=400M` ran cog for 35s at
**352 MB RSS**, no OOM kill, `dmesg` clean. (The segfault in the log is my own `pkill` at cleanup,
not a crash under pressure.)

## 4. CPU load

**~24% user, ~69% idle** on the Pi 4 at 1080p — *while the live Chromium kiosk was also running*.
CPU is not the constraint.

## 5. Rendering — first pass FAILED, fix applied, second pass PASSES

**First pass (commit `ca10929`): compact tiles lost their team codes and scores entirely.** League
chip, inning, bases and flag rendered, but `HOU 1 · SF 4` was simply absent — fatal for a
scoreboard.

**Cause:** `.rows` carried `overflow:hidden`. Under WebKit the size-contained tile's container
height resolves differently than Blink, the flex row band collapses, and `overflow:hidden` then
clips the team line away instead of merely overflowing it.

**Fix (commit `9aa45f0`):**
- dropped `overflow:hidden` from `.rows`, using `min-height:min-content` so the band cannot collapse
- floored `.trow` at `min-height:1em`
- added an `@supports not (font-size: 1cqh)` fallback that sizes tile text off the viewport for
  engines without usable container-query units
- Chromium regression-checked afterwards: 0 blank team rows, 0 overflow.

**Second pass renders correctly.** Confirmed present at 1080p: every compact tile's team codes and
scores (`HOU 1/SF 4`, `KC 1/LAD 1`, `TEX 2/LAA 3`, `COL 3/ARI 2`, `TB 12/ATH 2`, `SEA 1/NYY 4`),
favourite-team stars (`★NYY`, `★OSU`, `★UGA`), bases diamonds with the occupied base lit, flag
pills (`RISP`, `ONE SCORE`), the full ALSO ON sidebar, both webfonts, the neon palette, the CRT
overlay, HUD counters, and the static headline rotator with league badge + progress dots.
Live data updates between captures.

### Remaining cosmetic defects (not blockers)

1. **Team codes render dim.** The codes are drawn in each team's accent colour with a glow via
   `text-shadow: 0 0 8px color-mix(in srgb, var(--team) 60%, transparent)`. WebKit does not appear
   to apply that glow, so dark accents (navy, black, brown — MIL, SD, SEA) sit dark-on-dark and are
   weak from a distance. Fix: brighten dark accents or use a plain-rgba text-shadow fallback.
2. **The featured tile's LEADERS line is clipped** mid-line.
3. The featured tile has more dead space under WebKit than under Chromium.

All three are CSS-level and would not block a product build.

## 6. Screenshot paths (on the Pi)

- `~/cog-test/render-01.png` — first pass, 720p, **shows the missing-scores bug**
- `~/cog-test/render-02.png` — first pass +2 min, proves live data updating
- `~/cog-test/render-03-fixed-1080p.png` — after fix, windowed
- `~/cog-test/render-05.png` — **after fix, true 1920×1080 fullscreen (the definitive one)**

## 7. Verdict

**Q1 — renders correctly in WebKit? YES, after a one-line-class CSS fix.** It failed initially,
the cause was found and fixed, and the re-test shows all critical content present and correct. Two
cosmetic issues remain (dim team codes, clipped leaders line), both CSS-level.

**Q2 — fits in ~400MB? YES, and now proven at 1080p.** 355 MB unconstrained, 352 MB under a hard
400 MB cap, no OOM, and essentially flat between 720p and 1080p.

## 8. Live display confirmation

- `dorm-sports-wire.service` — **active throughout**, never stopped, restarted, disabled or edited.
- The fix was tested via a **separate clone on port 5001**, specifically to avoid restarting the
  live service. Port 5000 served the whole time (`/all` → 200 at the end).
- TV Chromium kiosk — still running (11 procs), still on `http://127.0.0.1:5000/board?scale=1.0`.
- TV compositor `wayland-0` untouched; all rendering used `wayland-1`.
- Live repo — `git status` clean, **0 files modified**.
- No reboot, no config file touched, no service edited, no package removed or upgraded.
- All test processes (cog, headless labwc, test Flask, Xvfb) cleaned up; packages left installed.

## Plain-language summary

**Would this dashboard work on a 512MB board? Yes — on the memory evidence, with a caveat about
headroom.**

WebKit renders this board in **355 MB at full 1080p**, held under a hard 400 MB ceiling without
being killed, and used about a quarter of one Pi 4's CPU. Memory was flat from 720p to 1080p,
which means the cost is the DOM and JS rather than the framebuffer — so a smaller/cheaper board
should behave similarly.

The rendering blocker found in the first pass was real but shallow: one `overflow:hidden` that
WebKit and Chromium disagree about. Fixed and re-verified. What is left is cosmetic — the team
codes need more contrast under WebKit because the glow effect does not apply.

**Honest caveats before you move the BOM to a Zero 2 W:**

1. **355 MB on a 512MB board leaves ~150MB for the OS, compositor and Python backend.** That is
   workable but not generous. If the Flask backend also runs on the same board, measure the whole
   stack together, not just the browser.
2. **This was measured on a Pi 4, not a Zero 2 W.** The Zero 2 W has a slower CPU and much less
   memory bandwidth; memory should be similar but *responsiveness* (the 8s headline swaps, the
   focus rotation, the TD animation) is unproven on that silicon.
3. Fix the two cosmetic issues before shipping — dim team codes are a real legibility problem on a
   scoreboard viewed from across a room.

So: **PASS on both questions**, with the recommendation that the next test is the whole stack
(backend + browser) on actual Zero 2 W hardware rather than more work on the Pi 4.
