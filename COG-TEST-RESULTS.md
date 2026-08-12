# P1 — cog / WebKit render + memory test on the dorm Pi 4

Run: 2026-08-11, over SSH against the live dorm Pi (Raspberry Pi 4 Model B Rev 1.5, 2GB).
Read-mostly. The live display was never interrupted (verified, see §8).

## 1. Browser used

| | |
|---|---|
| Browser | **cog 0.18.4** (the real target, no fallback needed) |
| Engine | **WPE WebKit 2.48.3** |
| Extra packages added | `xvfb`, `x11-utils`, `imagemagick`, `cog`, `grim`, `libwpebackend-fdo-1.0-1` |
| Packages removed/changed | **none** (additive only, no upgrades) |

Two setup notes worth recording for the product build:

- **`cog` has no X11 backend on Debian 13** — only `drm`, `headless`, and `wl` (Wayland). So the
  Xvfb approach in the brief cannot drive it. I ran a second, headless **wlroots compositor**
  (`labwc` with `WLR_BACKENDS=headless`) on its own socket `wayland-1`. The TV's real compositor
  is `wayland-0` and was never touched.
- `cog` also needs **`libwpebackend-fdo`**, which is not pulled in automatically. Without it cog
  aborts with `libWPEBackend-default.so: cannot open shared object file`.

## 2. Peak memory

Measured with `ps` (RSS), three processes, at 1280×720 headless output:

| Process | RSS |
|---|---|
| `cog` (UI) | 105 MB |
| `WPEWebProcess` (renderer) | 192 MB |
| `WPENetworkProcess` | 68 MB |
| **Total** | **357 MB** |

Chromium on the same Pi, for comparison, runs ~10 processes.

⚠️ **Caveat: this is at 720p, not 1080p.** The headless wlroots output defaulted to 1280×720 and
I did not get it to 1920×1080 within this run. Renderer memory scales with framebuffer/compositing
surface, so the 1080p figure will be **higher than 357 MB** — I would not assume it stays under
400 MB at 1080p without re-measuring. This is the single biggest open question in this test.

## 3. 400MB cap

**Survived.** `systemd-run --user --scope -p MemoryMax=400M` ran cog for 35s at **351 MB RSS**
with no OOM kill (`dmesg` clean, no kernel kill message). The segfault line in the log is from
*my own* `pkill` during cleanup, not a crash under memory pressure.

Again: survived at 720p. Not proven at 1080p.

## 4. CPU load

~**19–21% user, 3% sys, 76–78% idle** on the Pi 4 while rendering — and that is *on top of* the
live Chromium kiosk already running. CPU is not the constraint.

## 5. Rendering errors / missing content

**This is where it fails.** See §7.

- The **team abbreviations and scores are missing from the compact game tiles.** The tiles render
  their league chip, the inning/detail, the bases diamond, and the flag pill — but the actual
  `HOU 1 · SF 4` line is absent. That is the single most important content on the board.
- On the **featured tile** the codes *do* appear (`MIL Brewers 1` / `TEX Rangers 2`) but render
  dim and undersized versus Chromium.
- The **LEADERS line is clipped** mid-sentence (`Campusano 2-3, HR, 3 RBI, 2 R, BB` cut off).
- CFB tiles (which have no bases graphic) *do* show their team codes, just dimly.

**Everything else renders correctly**: layout, grid, sidebar, neon palette, CRT scanline overlay,
both webfonts (Press Start 2P + VT323), the favourite-team stars, the flag pills
(`ONE SCORE` / `RISP` / `TIE GAME`), and the new static headline rotator with its league badge and
progress dots. No console errors were logged by cog beyond a harmless a11y-bus warning.

**Live data updates fine.** render-01 and render-02 (2 min apart) show a different featured game,
different sidebar contents, and a different wire headline.

### Likely cause (and why it is probably fixable)

The tile text was recently changed to size itself in **container-query units** (`cqh`) off a
`container-type: size` tile, with `.rows { flex:1; overflow:hidden }`. Chromium resolves this fine;
WebKit appears to resolve the container height differently, so the rows box collapses and
`overflow:hidden` clips the team line away entirely. The compact tiles that *do* show codes are
the ones without the bases graphic competing for space — consistent with that theory.

This is a **frontend incompatibility in one recent styling decision**, not evidence that the
dashboard fundamentally cannot run on WebKit.

## 6. Screenshot paths

On the Pi:

- `~/cog-test/render-01.png` — initial render (1280×720)
- `~/cog-test/render-02.png` — ~2 min later, proves live data updating
- `~/cog-test/cq.png` — same as render-02

## 7. Verdict

**Q1 — does it render correctly in WebKit? NO, not as-is.** The board is recognisably itself and
~90% correct, but the compact tiles lose their scores, which is the core function of a scoreboard.
Not shippable in this state. Fixable: add a non-`cqh` fallback for tile text sizing (and drop the
`overflow:hidden` on `.rows`), then re-test.

**Q2 — does it fit in ~400MB? PROVISIONALLY YES.** 357 MB unconstrained, 351 MB under a hard
400 MB cap, no OOM. But **only proven at 720p** — the 1080p number is unmeasured and will be
higher.

## 8. Live display confirmation

- `dorm-sports-wire.service` — **active the entire time**, never stopped, restarted, or edited.
- TV Chromium kiosk — still running (10 procs), still on `http://127.0.0.1:5000/board?scale=1.0`.
- TV compositor socket `wayland-0` — present and untouched; all test rendering used `wayland-1`.
- Project repo — `git status` clean, **no existing file modified**.
- No reboot, no config file touched, no service edited, no package removed or upgraded.
- Service count went 27 → 26; the difference is a transient system service (`packagekit`-class,
  which exits on its own when idle), **not** the display service.

## Plain-language summary

**Would this dashboard work on a 512MB board? Not today — but the blocker is the frontend, not
the memory.**

The memory story is genuinely encouraging: WebKit renders this board in ~357 MB where Chromium
needs roughly triple that, and it held under a hard 400 MB ceiling without being killed. On CPU
it is comfortable.

The blocker is that the compact tiles lose their team names and scores under WebKit, which traces
to one recent CSS choice (container-query units) rather than anything deep. Fixing that is a
contained frontend job — likely an hour or two — after which this deserves a proper re-test.

**Two things to settle before betting the BOM on a Zero 2 W:**

1. **Re-measure at 1920×1080.** 357 MB at 720p is not 357 MB at 1080p, and 400 MB is not a lot of
   headroom. If it lands at 450–500 MB, a 512MB board is too tight to be comfortable regardless of
   rendering.
2. **Fix the `cqh` sizing and confirm the scores come back**, then screenshot again.

So: a promising partial pass, not a green light. Treat it as "worth the frontend fix and a 1080p
re-run", not as "the Zero 2 W works".
