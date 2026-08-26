/* ============================================================
   Dorm Wire — UI scale (readability from across the room)

   The browser cannot know a screen's PHYSICAL size: a 55" TV and a
   24" monitor at 1080p are identical in CSS pixels. So "auto-fit to
   the TV" is impossible in the strict sense. Instead:

     1. auto-pick a sensible default from the resolution, then
     2. let the value be overridden per device and REMEMBERED.

   Resolution order (first wins):
     ?scale=1.4   URL param  (also persists it)
     localStorage dormwire.scale   (set from /control or the URL)
     auto default by viewport size

   Exposes window.uiScale() -> current number, and
   window.setUiScale(n) -> apply + persist (used by /control).
   Boards read it to also thin out tile counts as text grows.
   ============================================================ */
(function () {
  "use strict";

  var KEY = "dormwire.scale";
  var MIN = 0.8, MAX = 2.5;

  function clampScale(n) {
    n = parseFloat(n);
    if (!isFinite(n)) return null;
    return Math.min(MAX, Math.max(MIN, n));
  }

  // Auto default: bigger panels/resolutions get a bigger multiplier so text
  // does not shrink into the caps. Tuned for a TV viewed across a room.
  // Tile text is sized in container units (cqh), so it ALREADY scales with the
  // panel: a 4K tile is bigger, so its text is bigger. Multiplying again by
  // resolution double-scales and overflows (this happened on a 65" 4K TV at
  // 1.9). Default to 1.0 everywhere and keep --s purely as a taste knob;
  // only nudge up on genuinely small panels where tiles get cramped.
  function autoScale() {
    var w = window.innerWidth || 1920;
    if (w < 1200) return 1.1;
    return 1.0;
  }

  function stored() {
    try { return clampScale(localStorage.getItem(KEY)); } catch (e) { return null; }
  }
  function persist(n) {
    try { localStorage.setItem(KEY, String(n)); } catch (e) {}
  }

  function fromUrl() {
    var m = /[?&]scale=([0-9.]+)/.exec(window.location.search);
    return m ? clampScale(m[1]) : null;
  }

  function apply(n) {
    document.documentElement.style.setProperty("--s", String(n));
    window.__uiScale = n;
    document.documentElement.setAttribute("data-scale", String(n));
  }

  var initial = fromUrl();
  if (initial != null) persist(initial);
  if (initial == null) initial = stored();
  if (initial == null) initial = autoScale();
  apply(initial);


  /* ---- ticker pacing ------------------------------------------------
     The crawl used a FIXED 95s duration, so its speed depended on how much
     content was loaded: more headlines = a wider track = faster scroll. Set
     the duration from the measured track width instead, for a constant,
     readable speed on any screen. Speed is tied to viewport width so it
     reads the same on a 1080p monitor and a 4K TV.                     */
  window.tuneTicker = function (sel) {
    var track = document.querySelector(sel || "#ticker-track");
    if (!track) return;
    var half = track.scrollWidth / 2;            // content is duplicated twice
    if (!half || !isFinite(half)) return;
    var secondsPerScreen = 34;                   // a full screen-width takes ~34s
    var pxPerSecond = (window.innerWidth || 1920) / secondsPerScreen;
    var duration = Math.max(40, Math.min(600, half / pxPerSecond));
    track.style.animationDuration = duration.toFixed(1) + "s";
  };


  /* ---- THE WIRE: static headline rotator --------------------------------
     Replaces the scrolling crawl. One headline sits still for HOLD_MS, then
     cross-fades to the next. Nothing moves while you read, so a Pi 4 at 4K
     stays smooth (the GPU only works during the ~400ms fade).            */
  var WIRE_HOLD_MS = 8000;
  function _wireEsc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }
  var _wireItems = [], _wireIdx = 0, _wireTimer = null;

  function _wireRender(fadeFirst) {
    var track = document.querySelector("#ticker-track");
    if (!track || !_wireItems.length) return;
    var it = _wireItems[_wireIdx % _wireItems.length];
    var slide = track.querySelector(".wire-slide");
    var paint = function () {
      var hot = (it.category || "") === "hot";
      var badge = (it.source || "WIRE").toUpperCase();
      var dots = _wireItems.map(function (_, i) {
        return '<i class="' + (i === _wireIdx % _wireItems.length ? "on" : "") + '"></i>';
      }).join("");
      track.innerHTML =
        '<div class="wire-slide">'
        + '<span class="wire-badge ' + (hot ? "hot" : "") + '">' + _wireEsc(badge) + "</span>"
        + '<span class="wire-text">' + _wireEsc(it.text) + "</span>"
        + '<span class="wire-dots">' + dots + "</span>"
        + "</div>";
    };
    if (fadeFirst && slide) {
      slide.classList.add("fade");
      setTimeout(paint, 380);
    } else {
      paint();
    }
  }

  window.setWire = function (items) {
    _wireItems = (items || []).filter(function (i) { return i && i.text; });
    _wireIdx = 0;
    clearInterval(_wireTimer);
    if (!_wireItems.length) return;
    _wireRender(false);
    _wireTimer = setInterval(function () {
      _wireIdx = (_wireIdx + 1) % _wireItems.length;
      _wireRender(true);
    }, WIRE_HOLD_MS);
  };


  /* ---- overscan safe area -------------------------------------------------
     Many TVs (especially older sets) zoom the HDMI picture ~3-5% and crop the
     edges, so the board gets cut off even though the Pi outputs a correct
     full frame. --safe pulls everything inward by N percent per side.
     Set per TV with ?safe=4, remembered like the scale knob. 0 = no inset.  */
  var SAFE_KEY = "dormwire.safe";
  function clampSafe(n){ n = parseFloat(n); return isFinite(n) ? Math.min(12, Math.max(0, n)) : null; }
  function applySafe(n){
    document.documentElement.style.setProperty("--safe", String(n));
    window.__uiSafe = n;
  }
  var safeUrl = (function(){ var m=/[?&]safe=([0-9.]+)/.exec(window.location.search); return m?clampSafe(m[1]):null; })();
  if (safeUrl != null) { try { localStorage.setItem(SAFE_KEY, String(safeUrl)); } catch(e){} }
  var safeVal = safeUrl;
  if (safeVal == null) { try { safeVal = clampSafe(localStorage.getItem(SAFE_KEY)); } catch(e){ safeVal = null; } }
  if (safeVal == null) safeVal = 0;
  applySafe(safeVal);
  window.uiSafe = function(){ return window.__uiSafe || 0; };
  window.setUiSafe = function(n){ var v = clampSafe(n); if (v==null) return window.uiSafe();
    try { localStorage.setItem(SAFE_KEY, String(v)); } catch(e){}
    applySafe(v); return v; };


  /* ---- board watcher ------------------------------------------------------
     /board is a SERVER-SIDE redirect, so it is evaluated exactly once: at page
     load. The kiosk resolved it at boot and then sat on that board forever —
     the day/time mode-switcher never re-fired (observed: still on the sports
     board at 1pm on a Wednesday, when /api/board correctly said "weekday").
     Poll the selector and navigate when the target board changes. Query args
     (scale, safe) are carried across so per-TV tuning survives the switch.  */
  var BOARD_POLL_MS = 60000;
  async function boardWatcher() {
    try {
      var r = await fetch("/api/board", { cache: "no-store" });
      if (!r.ok) return;
      var d = await r.json();
      var target = d && d.url;
      if (!target) return;
      if (target !== window.location.pathname) {
        window.location.href = target + window.location.search;
      }
    } catch (e) { /* offline: stay put and retry next tick */ }
  }
  setInterval(boardWatcher, BOARD_POLL_MS);
  setTimeout(boardWatcher, 5000);   // also check shortly after load

  window.uiScale = function () { return window.__uiScale || 1; };

  // Bigger text means fewer tiles fit on screen. Boards call this to thin the
  // grid instead of overflowing. base = count that fits at scale 1.
  window.tileBudget = function (base, min) {
    var s = window.uiScale();
    if (s <= 1.05) return base;
    var n = Math.round(base / (s * s));   // area-ish falloff
    return Math.max(min || 2, Math.min(base, n));
  };
  window.setUiScale = function (n) {
    var v = clampScale(n);
    if (v == null) return window.uiScale();
    persist(v);
    apply(v);
    // Boards re-render on their own polling cycle; nudge any listener now.
    window.dispatchEvent(new Event("uiscalechange"));
    return v;
  };
  window.resetUiScale = function () {
    try { localStorage.removeItem(KEY); } catch (e) {}
    apply(autoScale());
    window.dispatchEvent(new Event("uiscalechange"));
    return window.uiScale();
  };
})();
