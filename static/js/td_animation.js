/* ============================================================
   Dorm Wire — per-type Touchdown Animation
   Defines global fireTdAnimation(kind, playerText). Mounts into the
   existing #td-anim overlay on the football board. Self-injects CSS,
   auto-cleans after ~5.5s. kind: "passing" | "rushing" | "receiving".
   ============================================================ */
(function () {
  "use strict";

  var TD_SOUND = false;            // set true for an 8-bit fanfare
  var TEAM_ACCENT = "#4ac3ff";     // ball-carrier jersey/helmet color

  var styleInjected = false;
  var actx = null;

  function injectCSS() {
    if (styleInjected) return;
    styleInjected = true;
    var css = ''
      + '#td-anim.td-scene{position:fixed;inset:0;z-index:9999;overflow:hidden;'
      +   'background:radial-gradient(circle at 50% 120%,rgba(255,47,185,.18),transparent 55%),#04020a;'
      +   'font-family:"VT323",monospace;color:#f4f6ff;display:block;}'
      + '#td-anim.td-scene::after{content:"";position:absolute;inset:0;pointer-events:none;'
      +   'background:repeating-linear-gradient(0deg,rgba(0,0,0,.32) 0 1px,transparent 1px 3px);opacity:.4;}'
      + '.td-crowd{position:absolute;top:0;left:0;right:0;height:12%;display:flex;align-items:flex-end;gap:3px;'
      +   'padding:0 4px;background:linear-gradient(180deg,#120a2b,#0a0618);border-bottom:2px solid rgba(255,255,255,.08);overflow:hidden;}'
      + '.td-fan{flex:0 0 auto;}'
      + '.td-fan .fh{width:9px;height:9px;margin:0 auto;border-radius:50%;}'
      + '.td-fan .fb{width:11px;height:16px;opacity:.7;}'
      + '.td-crowd.cheer .td-fan{animation:tdjump .5s ease;}'
      + '@keyframes tdjump{30%{transform:translateY(-14px);}60%{transform:translateY(-5px);}}'
      + '.td-turf{position:absolute;left:0;right:0;bottom:0;height:52%;background:#07130a;'
      +   'border-top:3px solid rgba(255,255,255,.18);'
      +   'background-image:repeating-linear-gradient(90deg,rgba(255,255,255,.13) 0 3px,transparent 3px 9%);}'
      + '.td-ez{position:absolute;top:0;bottom:0;right:0;width:13%;border-left:4px solid #fff;'
      +   'background:repeating-linear-gradient(90deg,rgba(255,47,185,.28) 0 8px,rgba(255,47,185,.12) 8px 16px);'
      +   'display:grid;place-items:center;}'
      + '.td-ez span{font-family:"Press Start 2P",monospace;font-size:2vw;color:#fff;opacity:.5;writing-mode:vertical-rl;text-shadow:0 0 10px #ff2fb9;}'
      + '.td-player,.td-qb{position:absolute;bottom:9%;width:5vw;min-width:44px;text-align:center;z-index:3;}'
      + '.td-qb{left:8%;opacity:0;}'
      + '.td-hd{width:64%;max-width:34px;height:2.4vw;min-height:22px;margin:0 auto;background:var(--tdc);'
      +   'border-radius:44% 44% 12% 12%;position:relative;box-shadow:inset -4px 0 0 rgba(0,0,0,.25);}'
      + '.td-hd::after{content:"";position:absolute;bottom:22%;right:-4px;width:8px;height:8px;'
      +   'border:2px solid #d8d8d8;border-left:none;border-radius:0 4px 4px 0;}'
      + '.td-pads{width:100%;height:1.1vw;min-height:9px;margin:2px auto 0;background:#c9ccd6;border-radius:7px;}'
      + '.td-body{width:78%;height:2.6vw;min-height:22px;margin:0 auto;background:var(--tdc);'
      +   'box-shadow:inset 0 -4px 0 rgba(0,0,0,.28);}'
      + '.td-arms{position:absolute;top:34%;left:0;right:0;display:flex;justify-content:space-between;padding:0 2px;z-index:-1;}'
      + '.td-arm{width:22%;max-width:9px;height:2vw;min-height:16px;background:var(--tdc);border-radius:3px;}'
      + '.td-legs{display:flex;justify-content:center;gap:6px;margin-top:2px;}'
      + '.td-leg{width:26%;max-width:11px;height:1.7vw;min-height:14px;background:#2b2f3a;}'
      + '.running .td-leg:nth-child(1){animation:tdstep .16s infinite;}'
      + '.running .td-leg:nth-child(2){animation:tdstep .16s infinite .08s;}'
      + '.running .td-arm{animation:tdpump .16s infinite;}'
      + '.running .td-arm:last-child{animation:tdpump .16s infinite .08s;}'
      + '@keyframes tdstep{50%{transform:translateY(-5px) scaleY(.82);}}'
      + '@keyframes tdpump{50%{transform:translateY(-4px) rotate(12deg);}}'
      + '.td-ball{position:absolute;right:-4px;top:38%;width:15px;height:9px;background:#ffd23a;border-radius:50%;'
      +   'box-shadow:0 0 8px #ffd23a;transform:rotate(-20deg);}'
      + '.td-passball{position:absolute;bottom:26%;left:12%;width:17px;height:10px;background:#ffd23a;border-radius:50%;'
      +   'box-shadow:0 0 12px #ffd23a;transform:rotate(-20deg);opacity:0;z-index:4;}'
      + '.td-banner{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;'
      +   'gap:1.4vh;opacity:0;z-index:7;pointer-events:none;transition:opacity .2s;}'
      + '.td-banner.show{opacity:1;}'
      + '.td-big{font-family:"Press Start 2P",monospace;font-size:6vw;color:#ffd23a;'
      +   'text-shadow:0 0 4px #fff,0 0 22px #ffd23a,0 0 38px #ff2fb9;animation:tdflash .35s steps(2) infinite;}'
      + '@keyframes tdflash{50%{color:#fff;}}'
      + '.td-sub{font-size:3.4vw;color:#23f0ff;text-shadow:0 0 12px #23f0ff;text-align:center;}'
      + '.td-kind{font-family:"Press Start 2P",monospace;font-size:1.3vw;color:#06030d;background:#ffd23a;padding:.5em .7em;margin-top:.4vh;}'
      + '.td-fw{position:absolute;inset:0;z-index:6;pointer-events:none;}'
      + '.td-spark{position:absolute;width:10px;height:10px;}';
    var s = document.createElement("style");
    s.id = "td-anim-style";
    s.textContent = css;
    document.head.appendChild(s);
  }

  function anim(el, frames, opts) {
    if (el && typeof el.animate === "function") return el.animate(frames, opts);
    return { finished: Promise.resolve(), cancel: function () {} };
  }

  function beep(freq, start, dur) {
    var o = actx.createOscillator(), g = actx.createGain();
    o.type = "square"; o.frequency.value = freq;
    o.connect(g); g.connect(actx.destination);
    g.gain.setValueAtTime(0.0001, actx.currentTime + start);
    g.gain.exponentialRampToValueAtTime(0.16, actx.currentTime + start + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, actx.currentTime + start + dur);
    o.start(actx.currentTime + start); o.stop(actx.currentTime + start + dur + 0.02);
  }
  function fanfare() {
    if (!TD_SOUND) return;
    try {
      if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
      if (actx.state === "suspended") actx.resume();
      [523, 659, 784, 1047].forEach(function (f, i) { beep(f, i * 0.11, 0.14); });
      beep(1047, 0.44, 0.30); beep(1319, 0.44, 0.30);
    } catch (e) {}
  }

  function buildCrowd(host) {
    var cols = ["#ff2fb9", "#23f0ff", "#ffd23a", "#39ff14", "#ff6b6b", "#a06bff"];
    var crowd = host.querySelector(".td-crowd");
    var html = "";
    for (var i = 0; i < 60; i++) {
      var c = cols[i % cols.length];
      html += '<div class="td-fan" style="animation-delay:' + (Math.random() * 0.25) + 's">'
        + '<div class="fh" style="background:' + c + '"></div>'
        + '<div class="fb" style="background:' + c + '"></div></div>';
    }
    crowd.innerHTML = html;
  }
  function fireworks(host, running) {
    var fw = host.querySelector(".td-fw");
    var cols = ["#ffd23a", "#23f0ff", "#ff2fb9", "#39ff14", "#ff6b6b"];
    for (var i = 0; i < 34; i++) {
      var s = document.createElement("div");
      s.className = "td-spark";
      s.style.background = cols[i % cols.length];
      s.style.left = (35 + Math.random() * 30) + "%";
      s.style.top = (28 + Math.random() * 22) + "%";
      fw.appendChild(s);
      var ang = Math.random() * Math.PI * 2, dist = 70 + Math.random() * 120;
      running.push(anim(s, [
        { transform: "translate(0,0) scale(1)", opacity: 1 },
        { transform: "translate(" + Math.cos(ang) * dist + "px," + Math.sin(ang) * dist + "px) scale(0)", opacity: 0 }
      ], { duration: 950 + Math.random() * 550, easing: "ease-out", fill: "forwards" }));
    }
  }

  function celebrate(host, kind, playerText, running) {
    var banner = host.querySelector(".td-banner");
    host.querySelector(".td-sub").textContent = playerText || "";
    host.querySelector(".td-kind").textContent = (String(kind || "").toUpperCase() || "SCORE") + " TOUCHDOWN";
    banner.classList.add("show");
    host.querySelector(".td-crowd").classList.add("cheer");
    fireworks(host, running);
    fanfare();
  }

  window.fireTdAnimation = function (kind, playerText) {
    injectCSS();
    var host = document.getElementById("td-anim");
    if (!host) return;
    kind = (kind || "rushing").toLowerCase();

    host.className = "td-scene";
    host.style.display = "block";
    host.style.setProperty("--tdc", TEAM_ACCENT);
    host.innerHTML =
      '<div class="td-crowd"></div>'
      + '<div class="td-turf">'
      +   '<div class="td-ez"><span>TD</span></div>'
      +   '<div class="td-qb"><div class="td-hd"></div><div class="td-pads"></div><div class="td-body"></div></div>'
      +   '<div class="td-player">'
      +     '<div class="td-hd"></div>'
      +     '<div class="td-arms"><span class="td-arm"></span><span class="td-arm"></span></div>'
      +     '<div class="td-pads"></div><div class="td-body"></div>'
      +     '<div class="td-legs"><span class="td-leg"></span><span class="td-leg"></span></div>'
      +     '<div class="td-ball"></div>'
      +   '</div>'
      +   '<div class="td-passball"></div>'
      + '</div>'
      + '<div class="td-banner"><div class="td-big">TOUCHDOWN</div><div class="td-sub"></div><div class="td-kind"></div></div>'
      + '<div class="td-fw"></div>';

    buildCrowd(host);

    var player = host.querySelector(".td-player");
    var qb = host.querySelector(".td-qb");
    var passball = host.querySelector(".td-passball");
    var tuck = host.querySelector(".td-ball");
    var W = host.clientWidth || window.innerWidth || 900;
    var running = [];
    host._tdRunning = running;

    if (kind === "rushing") {
      player.style.left = "12%";
      player.classList.add("running");
      var run = anim(player, [{ transform: "translateX(0)" }, { transform: "translateX(" + (W * 0.66) + "px)" }],
        { duration: 1600, easing: "ease-in", fill: "forwards" });
      running.push(run);
      run.finished.then(function () { player.classList.remove("running"); celebrate(host, kind, playerText, running); })
        .catch(function () {});
    } else {
      qb.style.opacity = "1";
      player.style.left = "56%";
      tuck.style.opacity = "0";
      passball.style.opacity = "1";
      var startX = W * 0.10, endX = W * 0.56;
      var arc = anim(passball, [
        { transform: "translate(0,0) rotate(-20deg)", offset: 0 },
        { transform: "translate(" + ((endX - startX) * 0.5) + "px,-16vh) rotate(80deg)", offset: 0.5 },
        { transform: "translate(" + (endX - startX) + "px,1vh) rotate(210deg)", offset: 1 }
      ], { duration: 1050, easing: "ease-out", fill: "forwards" });
      running.push(arc);
      arc.finished.then(function () {
        passball.style.opacity = "0"; tuck.style.opacity = "1";
        player.classList.add("running");
        var run2 = anim(player, [{ transform: "translateX(0)" }, { transform: "translateX(" + (W * 0.13) + "px)" }],
          { duration: 700, easing: "ease-in", fill: "forwards" });
        running.push(run2);
        return run2.finished;
      }).then(function () { player.classList.remove("running"); celebrate(host, kind, playerText, running); })
        .catch(function () {});
    }

    clearTimeout(host._tdTimer);
    host._tdTimer = setTimeout(function () {
      (host._tdRunning || []).forEach(function (a) { try { a.cancel && a.cancel(); } catch (e) {} });
      host.style.display = "none";
      host.className = "";
      host.innerHTML = "";
    }, 5600);
  };
})();
