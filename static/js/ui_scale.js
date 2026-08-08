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
  function autoScale() {
    var w = window.innerWidth || 1920;
    if (w >= 3200) return 1.9;   // 4K panel
    if (w >= 2400) return 1.5;   // 1440p+
    if (w >= 1800) return 1.35;  // 1080p TV (the dorm case)
    if (w >= 1400) return 1.15;
    return 1.0;                  // small monitor / laptop
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
