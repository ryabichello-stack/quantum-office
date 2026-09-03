/**
 * DELNO widget embed loader (E3.4).
 *
 * Usage:
 * <script src="https://cdn.dlno.ru/widget/v1/embed.js"
 *         data-site-key="YOUR_SITE_KEY"
 *         data-theme="auto"
 *         async></script>
 */
(function () {
  "use strict";

  var script = document.currentScript;
  if (!script) return;

  var siteKey = script.getAttribute("data-site-key") || "demo_dlno";
  var theme = (script.getAttribute("data-theme") || "auto").toLowerCase();
  var api = script.getAttribute("data-api") || "https://api.dlno.ru/v1/public/widget";
  var cdn = (script.getAttribute("data-cdn") || "https://cdn.dlno.ru/widget/v1").replace(/\/$/, "");
  var zIndex = script.getAttribute("data-z-index") || "2147483000";

  var page = "index.html";
  if (theme === "light") page = "light.html";
  if (theme === "dark") page = "dark.html";

  var src =
    cdn +
    "/" +
    page +
    "?embed=1&site_key=" +
    encodeURIComponent(siteKey) +
    "&api=" +
    encodeURIComponent(api);

  var iframe = document.createElement("iframe");
  iframe.title = "DELNO assistant";
  iframe.setAttribute("aria-label", "DELNO — ИИ-сотрудник");
  iframe.src = src;
  iframe.allow = "microphone";
  iframe.style.cssText =
    "position:fixed;bottom:0;left:50%;transform:translateX(-50%);" +
    "width:min(420px,100vw);height:min(720px,100vh);border:0;background:transparent;" +
    "z-index:" +
    zIndex +
    ";pointer-events:auto;";

  if (document.body) {
    document.body.appendChild(iframe);
  } else {
    document.addEventListener("DOMContentLoaded", function () {
      document.body.appendChild(iframe);
    });
  }
})();
