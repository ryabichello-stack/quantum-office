/**
 * Auto light/dark contrast for Crystal Widget on host page background.
 */
(function () {
  "use strict";

  var root = document.documentElement;
  var mount = document.querySelector(".delno-crystal-mount");

  function parseColor(str) {
    var m = String(str).match(/rgba?\(([^)]+)\)/i);
    if (!m) return null;
    var p = m[1].split(",").map(function (v) {
      return parseFloat(v.trim());
    });
    return { r: p[0] || 0, g: p[1] || 0, b: p[2] || 0, a: p.length > 3 ? p[3] : 1 };
  }

  function lum(c) {
    return 0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
  }

  function detect() {
    if (!mount) return;
    var els = document.elementsFromPoint
      ? document.elementsFromPoint(window.innerWidth / 2, window.innerHeight - 60)
      : [];
    var c = null;
    for (var i = 0; i < els.length && !c; i++) {
      if (els[i].closest && (els[i].closest(".widget") || els[i].closest(".panel"))) continue;
      var n = els[i];
      while (n && n !== document.documentElement) {
        var pc = parseColor(getComputedStyle(n).backgroundColor);
        if (pc && pc.a > 0.55) {
          c = pc;
          break;
        }
        n = n.parentElement;
      }
    }
    if (!c) c = parseColor(getComputedStyle(document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
    mount.setAttribute("data-contrast", lum(c) < 145 ? "light" : "dark");
  }

  window.addEventListener("resize", detect, { passive: true });
  window.addEventListener("scroll", detect, { passive: true });
  setTimeout(detect, 50);
})();
