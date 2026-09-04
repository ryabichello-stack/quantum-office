(() => {
  const BASE =
    typeof window !== "undefined" && window.__QC_BASE__
      ? String(window.__QC_BASE__)
      : location.pathname.indexOf("/_quantum_console") === 0
        ? "/_quantum_console"
        : "";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor("secondary_bg_color");
      if (tg.setBackgroundColor) tg.setBackgroundColor("bg_color");
    } catch (_) {}
  }

  const $ = (id) => document.getElementById(id);

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtNum(v) {
    if (v == null || v === "") return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return String(v);
    return n.toLocaleString("ru-RU");
  }

  function fmtDur(sec) {
    if (sec == null || sec === "") return "—";
    const s = Math.round(Number(sec));
    if (Number.isNaN(s)) return "—";
    if (s < 60) return s + " с";
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m + " мин " + r + " с";
  }

  function fmtTime(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return String(iso).slice(11, 16) || String(iso);
      return d.toLocaleString("ru-RU", {
        timeZone: "Europe/Moscow",
        hour: "2-digit",
        minute: "2-digit",
        day: "2-digit",
        month: "2-digit",
      });
    } catch {
      return String(iso);
    }
  }

  function initDataHeader() {
    if (tg && tg.initData) return tg.initData;
    return "";
  }

  async function api(path) {
    const headers = {};
    const initData = initDataHeader();
    if (initData) headers["X-Telegram-Init-Data"] = initData;
    const res = await fetch(BASE + path, {
      credentials: "include",
      headers,
    });
    const text = await res.text();
    let data = null;
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
    if (!res.ok) {
      const msg = (data && (data.detail || data.error)) || res.statusText || "error";
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }

  function paint(data) {
    const m = (data && data.metrika) || {};
    const w = (data && data.webhook) || {};
    const day = (data && data.day) || "—";

    $("dayLine").textContent = "Данные за " + day + " (МСК)";
    $("kVisits").textContent = fmtNum(m.visits);
    $("kUsers").textContent = fmtNum(m.users);
    $("kViews").textContent = fmtNum(m.pageviews);
    $("kLeads").textContent = fmtNum(w.leads);

    const pill = $("metrikaPill");
    if (m.available) {
      pill.textContent = "ок";
      pill.className = "pill ok";
    } else {
      pill.textContent = "нет";
      pill.className = "pill bad";
    }
    $("mBounce").textContent =
      m.bounce_rate_pct != null ? fmtNum(m.bounce_rate_pct) + "%" : "—";
    $("mDur").textContent = fmtDur(m.avg_visit_duration_sec);
    $("mConv").textContent =
      w.conversion_pct != null ? fmtNum(w.conversion_pct) + "%" : "—";

    const err = $("metrikaErr");
    if (m.error) {
      err.hidden = false;
      err.textContent = m.error;
    } else {
      err.hidden = true;
      err.textContent = "";
    }

    $("leadsPill").textContent = String(w.leads || 0);
    const box = $("leadsBox");
    const recent = w.recent || [];
    if (!recent.length) {
      box.innerHTML = '<p class="muted">Заявок за сегодня пока нет</p>';
    } else {
      box.innerHTML = recent
        .map(
          (L) => `<article class="lead">
            <span class="name">${esc(L.name || "—")}</span>
            <span class="phone">${esc(L.phone || "—")}</span>
            <span class="when">${esc(fmtTime(L.created_at))}${
            L.page ? " · " + esc(L.page) : ""
          }</span>
          </article>`
        )
        .join("");
    }

    $("footLine").textContent =
      "Обновлено " +
      (data.generated_at
        ? new Date(data.generated_at).toLocaleTimeString("ru-RU", {
            timeZone: "Europe/Moscow",
            hour: "2-digit",
            minute: "2-digit",
          })
        : "—") +
      " МСК";
  }

  async function load() {
    try {
      $("dayLine").textContent = "Загрузка…";
      const data = await api("/api/miniapp/today");
      paint(data);
    } catch (e) {
      $("dayLine").textContent = e.message || String(e);
      $("leadsBox").innerHTML =
        '<p class="muted">Не удалось загрузить. Откройте Mini App из бота @Quantum_office_bot.</p>';
    }
  }

  if (tg && tg.MainButton) {
    try {
      tg.MainButton.setText("Обновить");
      tg.MainButton.show();
      tg.MainButton.onClick(() => {
        tg.MainButton.showProgress();
        load().finally(() => {
          try {
            tg.MainButton.hideProgress();
          } catch (_) {}
        });
      });
    } catch (_) {}
  }

  load();
})();
