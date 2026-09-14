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

  async function api(path) {
    const headers = {};
    const initData = tg && tg.initData ? tg.initData : "";
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

  function switchTab(name) {
    document.querySelectorAll(".tab").forEach((btn) => {
      const on = btn.getAttribute("data-tab") === name;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.hidden = panel.getAttribute("data-panel") !== name;
    });
    if (name === "outreach") loadOutreach(false);
    if (name === "calls") loadCalls(false);
  }

  function paintChannels(data) {
    const m = (data && data.metrika) || {};
    const w = (data && data.webhook) || {};
    $("dayLine").textContent = "Данные за " + ((data && data.day) || "—") + " (МСК)";
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

  function paintOutreach(data) {
    const err = $("oErr");
    if (!data || data.error) {
      err.hidden = false;
      err.textContent = (data && data.error) || "Не удалось загрузить outreach";
      return;
    }
    err.hidden = true;
    $("oSent").textContent = fmtNum(data.sent_today);
    $("oLimit").textContent = fmtNum(data.daily_limit);
    $("oLeft").textContent = fmtNum(data.remaining_today);
    $("oPending").textContent = fmtNum(data.pending);
    $("oDue").textContent = fmtNum(data.followups_due);
    $("oTotal").textContent = fmtNum(data.sent_total);
    const dmin = data.delay_min_min;
    const dmax = data.delay_max_min;
    $("oDelay").textContent =
      dmin != null && dmax != null ? dmin + "–" + dmax + " мин" : "—";
    $("oCb").textContent = fmtNum(data.callback_requests);
    const pill = $("oStatePill");
    pill.textContent = String(data.run_state_ru || data.run_state || "—");
    const raw = String(data.run_state || "").toLowerCase();
    pill.className =
      "pill " +
      (raw === "playing" || raw === "running"
        ? "ok"
        : raw === "paused"
          ? ""
          : "bad");
  }

  function paintCalls(data) {
    const box = $("callsBox");
    const pill = $("callsPill");
    if (!data || data.error) {
      pill.textContent = "!";
      pill.className = "pill bad";
      box.innerHTML =
        '<p class="muted">' +
        esc((data && data.error) || "Не удалось загрузить звонки") +
        "</p>";
      return;
    }
    const calls = data.calls || [];
    pill.textContent = String(data.total != null ? data.total : calls.length);
    pill.className = "pill";
    if (!calls.length) {
      box.innerHTML = '<p class="muted">Исходящих пока нет</p>';
      return;
    }
    box.innerHTML = calls
      .map((c) => {
        const dur =
          c.duration_seconds != null
            ? Math.round(Number(c.duration_seconds)) + " с"
            : "—";
        return `<article class="lead">
            <span class="name">${esc(c.phone || "—")}</span>
            <span class="phone">${esc(c.outcome || "—")}</span>
            <span class="when">${esc(fmtTime(c.start_time))} · ${esc(dur)}${
          c.name ? " · " + esc(c.name) : ""
        }</span>
          </article>`;
      })
      .join("");
  }

  let outreachLoaded = false;
  let callsLoaded = false;

  async function loadOutreach(force) {
    if (outreachLoaded && !force) return;
    try {
      $("oStatePill").textContent = "…";
      const data = await api("/api/miniapp/outreach");
      paintOutreach(data);
      outreachLoaded = true;
    } catch (e) {
      paintOutreach({ error: e.message || String(e) });
    }
  }

  async function loadCalls(force) {
    if (callsLoaded && !force) return;
    try {
      $("callsPill").textContent = "…";
      const data = await api("/api/miniapp/calls?limit=8");
      paintCalls(data);
      callsLoaded = true;
    } catch (e) {
      paintCalls({ error: e.message || String(e) });
    }
  }

  async function loadChannels() {
    try {
      $("dayLine").textContent = "Загрузка…";
      const data = await api("/api/miniapp/today");
      paintChannels(data);
    } catch (e) {
      $("dayLine").textContent = e.message || String(e);
      $("leadsBox").innerHTML =
        '<p class="muted">Не удалось загрузить. Откройте Mini App из бота @Quantum_office_bot.</p>';
    }
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab")));
  });

  document.querySelectorAll(".chip[data-copy]").forEach((btn) => {
    btn.setAttribute("data-label", btn.textContent || "");
    btn.addEventListener("click", async () => {
      const text = btn.getAttribute("data-copy") || "";
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        }
        if (tg && tg.showPopup) {
          tg.showPopup({
            title: "Скопировано",
            message: "Вставьте фразу в чат с ботом и отправьте.",
            buttons: [{ type: "close" }],
          });
        } else {
          btn.textContent = "Скопировано";
          setTimeout(() => {
            btn.textContent = btn.getAttribute("data-label") || "Ок";
          }, 1200);
        }
      } catch (_) {
        if (tg && tg.showAlert) tg.showAlert(text);
      }
    });
  });

  const closeBtn = $("closeToChat");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      try {
        if (tg && tg.close) tg.close();
      } catch (_) {}
    });
  }

  if (tg && tg.MainButton) {
    try {
      tg.MainButton.setText("Обновить");
      tg.MainButton.show();
      tg.MainButton.onClick(() => {
        tg.MainButton.showProgress();
        const active = document.querySelector(".tab.on");
        const tab = active ? active.getAttribute("data-tab") : "channels";
        const jobs = [loadChannels()];
        if (tab === "outreach") jobs.push(loadOutreach(true));
        if (tab === "calls") jobs.push(loadCalls(true));
        Promise.all(jobs).finally(() => {
          try {
            tg.MainButton.hideProgress();
          } catch (_) {}
        });
      });
    } catch (_) {}
  }

  loadChannels();
})();
