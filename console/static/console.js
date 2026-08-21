(() => {
  const $ = (id) => document.getElementById(id);
  const BASE =
    typeof window !== "undefined" && window.__QC_BASE__
      ? String(window.__QC_BASE__)
      : location.pathname.startsWith("/_quantum_console")
        ? "/_quantum_console"
        : "";

  // Brand assets from Mail.ru «Графика/Лого» (latest square orange mark)
  const LOGO_MARK = BASE + "/assets/brand/logo-mark.png";
  if ($("loginLogo")) $("loginLogo").src = LOGO_MARK;
  if ($("sideLogo")) $("sideLogo").src = LOGO_MARK;

  const TAB_META = {
    status: { title: "Пульт", hint: "Линия, робот, outreach, звонки и сервисы" },
    outreach: { title: "Outreach", hint: "Кампании по отраслям, очередь писем, звонки" },
    scenario: { title: "Сценарий", hint: "YAML-профили входящих и исходящих" },
    knowledge: { title: "База знаний", hint: "Second Brain · quantum_labs.md" },
    calls: { title: "Звонки", hint: "История и расшифровки" },
    campaign: { title: "Обзвон Sheets", hint: "База номеров из Google Sheet и скрипт кампании" },
    outbound: { title: "Задание на звонок", hint: "Номер, цель, тема — робот позвонит по заданию" },
    pack: { title: "Пакет / бэкап", hint: "Канонические пути и секреты" },
  };

  let currentUser = null;

  async function api(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const res = await fetch(BASE + path, {
      ...opts,
      headers,
      credentials: "include",
    });
    const text = await res.text();
    let data;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }
    if (res.status === 401 && path !== "/api/auth/login" && path !== "/api/auth/me") {
      showLogin("Сессия истекла — войдите снова");
      throw new Error(data.detail || "unauthorized");
    }
    if (!res.ok) throw new Error(data.detail || data.message || text || res.statusText);
    return data;
  }

  function pill(ok, label) {
    return `<span class="pill ${ok ? "ok" : "bad"}">${label}</span>`;
  }

  function esc(s) {
    return String(s || "").replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
  }

  /** ISO/UTC → «24.07.2026, 17:46:43» in Europe/Moscow */
  function fmtMsk(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    try {
      return new Intl.DateTimeFormat("ru-RU", {
        timeZone: "Europe/Moscow",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).format(d);
    } catch {
      return String(iso);
    }
  }

  function fmtDuration(sec) {
    if (sec === null || sec === undefined || sec === "") return "";
    const n = Number(sec);
    if (!Number.isFinite(n)) return String(sec);
    if (n < 60) return Math.round(n) + " с";
    const m = Math.floor(n / 60);
    const s = Math.round(n % 60);
    return m + " мин " + String(s).padStart(2, "0") + " с";
  }

  function showLogin(errMsg) {
    $("appShell").hidden = true;
    $("loginGate").hidden = false;
    if (errMsg) {
      $("loginErr").hidden = false;
      $("loginErr").textContent = errMsg;
    } else {
      $("loginErr").hidden = true;
      $("loginErr").textContent = "";
    }
    setTimeout(() => $("loginUser") && $("loginUser").focus(), 50);
  }

  function showApp(user) {
    currentUser = user || currentUser;
    $("loginGate").hidden = true;
    $("appShell").hidden = false;
    if ($("userLabel")) $("userLabel").textContent = currentUser || "admin";
  }

  async function checkAuth() {
    try {
      const me = await api("/api/auth/me");
      if (me && me.authenticated) {
        showApp(me.user || "admin");
        return true;
      }
    } catch (_) {
      /* fall through */
    }
    showLogin();
    return false;
  }

  async function doLogin(e) {
    if (e) e.preventDefault();
    const username = (($("loginUser") && $("loginUser").value) || "").trim();
    const password = ($("loginPass") && $("loginPass").value) || "";
    $("loginErr").hidden = true;
    try {
      const r = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      showApp(r.user || username);
      if ($("loginPass")) $("loginPass").value = "";
      await refreshAll();
    } catch (err) {
      $("loginErr").hidden = false;
      $("loginErr").textContent = err.message || "Ошибка входа";
    }
  }

  async function doLogout() {
    try {
      await api("/api/auth/logout", { method: "POST", body: "{}" });
    } catch (_) {
      /* ignore */
    }
    currentUser = null;
    showLogin();
  }

  let toolsCatalogCache = null;

  async function getToolsCatalog() {
    if (toolsCatalogCache) return toolsCatalogCache;
    toolsCatalogCache = await api("/api/tools");
    return toolsCatalogCache;
  }

  function selectedScenarioTools() {
    return Array.from(document.querySelectorAll("input.sc-tool:checked"))
      .filter((el) => !el.getAttribute("data-post-call"))
      .map((el) => el.value);
  }

  function renderScenarioTools(enabledNames, expandTool) {
    const box = $("scToolsPanel");
    if (!box) return;
    const cat = toolsCatalogCache || { tools: [] };
    const enabled = new Set(enabledNames || []);
    const tools = (cat.tools || []).filter(
      (t) => t.phase === "in_call" || t.phase === "post_call"
    );
    const groups = {};
    tools.forEach((t) => {
      const g = t.group_label || t.group || "Прочее";
      (groups[g] = groups[g] || []).push(t);
    });
    const order = ["Бизнес", "Телефония", "HTTP / интеграции", "После звонка", "Прочее"];
    const keys = [
      ...order.filter((k) => groups[k]),
      ...Object.keys(groups).filter((k) => !order.includes(k)),
    ];
    box.innerHTML = keys
      .map((g) => {
        const rows = groups[g]
          .map((t) => {
            const on = enabled.has(t.name);
            const open = expandTool && expandTool === t.name ? " open" : "";
            const phaseNote =
              t.phase === "post_call" ? "после звонка" : "во время звонка";
            return `<div class="tool-row${open}" data-tool-name="${esc(t.name)}">
              <div class="tool-row-main">
                <input type="checkbox" class="sc-tool" value="${esc(t.name)}" ${
                  on ? "checked" : ""
                } ${t.phase === "post_call" ? 'data-post-call="1"' : ""} />
                <div class="tool-row-text">
                  <div class="tool-row-title">${esc(t.label || t.name)}</div>
                  <div class="tool-row-meta">${esc(phaseNote)} · <code>${esc(t.name)}</code></div>
                </div>
                <span class="tool-chevron" aria-hidden="true">›</span>
              </div>
              <div class="tool-row-body">
                <p>${esc(t.description || "Нет описания — служебный tool AVA.")}</p>
                <p>Группа: ${esc(t.group_label || t.group || "—")} · источник: ${esc(
                  t.source || "—"
                )}</p>
                ${
                  t.phase === "post_call"
                    ? "<p class='muted'>Post-call на исходящих отключён (лиды только на входящих).</p>"
                    : ""
                }
              </div>
            </div>`;
          })
          .join("");
        return `<div class="tool-group-title">${esc(g)}</div>${rows}`;
      })
      .join("");

    box.querySelectorAll(".tool-row-main").forEach((main) => {
      main.addEventListener("click", (ev) => {
        if (ev.target && ev.target.matches("input.sc-tool")) return;
        const row = main.closest(".tool-row");
        if (row) row.classList.toggle("open");
      });
    });
    box.querySelectorAll("input.sc-tool").forEach((cb) => {
      cb.addEventListener("click", (ev) => ev.stopPropagation());
      cb.addEventListener("change", () => {
        if ($("scToolsHint")) {
          $("scToolsHint").textContent =
            "Включено in-call: " +
            selectedScenarioTools().length +
            " · нажмите «Сохранить профиль»";
        }
      });
    });

    if (expandTool) {
      const safe =
        typeof CSS !== "undefined" && CSS.escape
          ? CSS.escape(expandTool)
          : expandTool.replace(/"/g, '\\"');
      const row = box.querySelector(`.tool-row[data-tool-name="${safe}"]`);
      if (row) {
        row.classList.add("open");
        row.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
    if ($("scToolsHint")) {
      $("scToolsHint").textContent =
        "Включено in-call: " +
        selectedScenarioTools().length +
        " · нажмите «Сохранить профиль»";
    }
  }

  async function openScenarioTools(context, toolName) {
    if ($("scContext")) $("scContext").value = context || "default";
    setTab("scenario");
    try {
      await loadScenario(toolName || "");
      const block = $("scToolsBlock");
      if (block) block.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      alert(e.message);
    }
  }

  async function setInboundLine(enabled) {
    const res = await api("/api/line", {
      method: "POST",
      body: JSON.stringify({ enabled: !!enabled }),
    });
    return res;
  }

  async function loadStatus() {
    const s = await api("/api/status");
    const services = s.services || [];
    const unitsUi = s.units_ui || [];
    const profiles = s.profiles || {};
    const sipOk = !!s.mango_registered;
    const line = s.inbound_line || {};
    const lineOn = !!line.enabled;
    const robot = s.robot || {};
    const activity = s.activity || {};
    const recent = activity.recent_calls || [];
    const outreach = activity.outreach || null;
    const campaign = activity.campaign || null;
    const outbox = (outreach && outreach.outbox) || {};
    const runStateRaw = outreach ? String(outreach.run_state || "stopped") : "";
    const runLive = runStateRaw === "running" || runStateRaw === "scheduled";
    const runStateRu =
      runStateRaw === "running"
        ? "идёт"
        : runStateRaw === "scheduled"
          ? "по расписанию"
          : runStateRaw === "stopped" || runStateRaw === "paused"
            ? "стоп"
            : runStateRaw || "нет данных";

    function profileCard(key) {
      const p = profiles[key] || {};
      const tools = p.tools || [];
      const chips = tools.length
        ? tools
            .map(
              (t) =>
                `<button type="button" class="tool-chip" data-goto-context="${esc(
                  p.context || ""
                )}" data-tool="${esc(t.name)}" title="${esc(t.description || "")}">${esc(
                  t.label || t.name
                )}</button>`
            )
            .join("")
        : `<span class="muted">инструменты не включены</span>`;
      return `<div class="profile-card">
        <h3>${esc(p.label || key)}</h3>
        <div class="tool-chip-row">${chips}</div>
        <div class="actions">
          <button type="button" class="btn-quiet" data-goto-context="${esc(
            p.context || ""
          )}">Настроить</button>
        </div>
      </div>`;
    }

    const callsRows = recent.length
      ? recent
          .map((c) => {
            const ctx = c.context_name === "outbound" ? "исх." : "вх.";
            return `<tr class="call-row" data-call-id="${esc(c.call_id)}" tabindex="0">
              <td>${esc(fmtMsk(c.start_time))}</td>
              <td>${esc(c.caller_number || "—")}</td>
              <td>${esc(ctx)}</td>
              <td>${esc(fmtDuration(c.duration_seconds))}</td>
              <td>${esc(c.outcome || "—")}</td>
            </tr>`;
          })
          .join("")
      : `<tr><td colspan="5" class="muted">Пока нет записей</td></tr>`;

    $("statusBox").innerHTML = `
      <div class="pult-hero">
        <div class="pult-hero-copy">
          <p class="pult-kicker">Quantum Labs</p>
          <h2 class="pult-title">Пульт</h2>
          <p class="pult-sub">Линия · робот · письма · звонки</p>
        </div>
        <div class="pult-flags">
          ${pill(!!robot.ok, robot.ok ? "на приёме" : "не готов")}
          ${pill(sipOk, sipOk ? "SIP" : "нет SIP")}
          ${pill(lineOn, lineOn ? "линия вкл" : "линия выкл")}
        </div>
      </div>

      <div class="pult-controls">
        <div class="pult-card line-card ${lineOn ? "on" : "off"}">
          <div class="pult-card-top">
            <span class="pult-card-label">Входящая линия</span>
            <span class="pill ${lineOn ? "ok" : "bad"}">${lineOn ? "принимает" : "закрыта"}</span>
          </div>
          <p class="muted tight">Звонки на ИИ-секретаря</p>
          <div class="seg" role="group" aria-label="Автолиния">
            <button type="button" id="btnLineOn" class="${lineOn ? "seg-on" : ""}">Вкл</button>
            <button type="button" id="btnLineOff" class="${!lineOn ? "seg-on" : ""}">Выкл</button>
          </div>
          <p class="meta-line" id="lineMsg">${esc(line.value || "on")}</p>
        </div>

        <div class="pult-card">
          <div class="pult-card-top">
            <span class="pult-card-label">Робот</span>
            <span class="pill ${robot.ai_engine ? "ok" : "bad"}">${
              robot.ai_engine ? "в сети" : "нет связи"
            }</span>
          </div>
          <ul class="pult-checklist">
            <li>${pill(!!robot.ai_engine, "голос")}</li>
            <li>${pill(!!robot.sip, "SIP")}</li>
            <li>${pill(!!robot.line_enabled, "линия")}</li>
          </ul>
          <div class="actions">
            <button type="button" class="btn-quiet" data-goto-tab="scenario">Сценарий</button>
            <button type="button" class="btn-quiet" data-goto-tab="calls">Звонки</button>
          </div>
        </div>

        <div class="pult-card">
          <div class="pult-card-top">
            <span class="pult-card-label">Письма</span>
            <span class="pill ${runLive ? "ok" : ""}">${esc(runStateRu)}</span>
          </div>
          ${
            outreach
              ? `<p class="muted tight">Сегодня ${esc(
                  outreach.today_sent ?? 0
                )} / лимит ${esc(
                  outreach.effective_daily_limit ?? outreach.daily_limit ?? "—"
                )}</p>
                 <div class="pult-mini-grid">
                   <div><span class="label">очередь</span><b>${esc(outbox.pending ?? "—")}</b></div>
                   <div><span class="label">ушло</span><b>${esc(outbox.sent ?? "—")}</b></div>
                   <div><span class="label">ответы</span><b>${esc(outbox.replied ?? "—")}</b></div>
                   <div><span class="label">сбои</span><b>${esc(outbox.failed ?? "—")}</b></div>
                 </div>
                 <div class="actions">
                   <button type="button" class="btn-quiet" data-goto-tab="outreach">Открыть</button>
                 </div>`
              : `<p class="muted tight">Нет данных</p>
                 <div class="actions"><button type="button" class="btn-quiet" data-goto-tab="outreach">Открыть</button></div>`
          }
        </div>

        <div class="pult-card">
          <div class="pult-card-top">
            <span class="pult-card-label">Обзвон</span>
            <span class="pill ${campaign && campaign.running ? "ok" : ""}">${
              campaign && campaign.running ? "идёт" : "пауза"
            }</span>
          </div>
          ${
            campaign
              ? `<div class="pult-mini-grid">
                   <div><span class="label">сделано</span><b>${esc(campaign.processed ?? "—")}</b></div>
                   <div><span class="label">интерес</span><b>${esc(campaign.interested ?? "—")}</b></div>
                   <div><span class="label">ошибки</span><b>${esc(campaign.errors ?? "—")}</b></div>
                   <div><span class="label">в листе</span><b>${esc(campaign.queued ?? "—")}</b></div>
                 </div>`
              : `<p class="muted tight">Нет данных кампании</p>`
          }
          <div class="actions">
            <button type="button" class="btn-quiet" data-goto-tab="campaign">Sheets</button>
            <button type="button" class="btn-quiet" data-goto-tab="outbound">Задание на звонок</button>
          </div>
          <div id="campaignGlance"></div>
        </div>
      </div>

      <div class="pult-section-head">
        <h2 class="section-title">Последние звонки</h2>
        <p class="muted tight">Нажмите строку — расшифровка</p>
      </div>
      <div class="surface-tight">
        <table class="calls-table"><thead><tr>
          <th>Время</th><th>Номер</th><th>Тип</th><th>Длит.</th><th>Исход</th>
        </tr></thead><tbody>${callsRows}</tbody></table>
      </div>

      <div class="pult-section-head">
        <h2 class="section-title">Сервисы</h2>
      </div>
      <div class="status-grid">
        ${services
          .map(
            (svc) =>
              `<div class="status-card ${svc.ok ? "ok" : "bad"}" title="${esc(svc.hint || "")}">
                <span class="label">${esc(svc.label || svc.id)}</span>
                <span class="value">${svc.ok ? "ок" : "нет"}</span>
              </div>`
          )
          .join("")}
      </div>

      <div class="pult-section-head">
        <h2 class="section-title">Инструменты</h2>
        <p class="muted tight">В сценарии входящих и исходящих</p>
      </div>
      <div class="profile-tools">
        ${profileCard("inbound")}
        ${profileCard("outbound")}
      </div>

      <details class="pult-details">
        <summary>Техническое</summary>
        <table><thead><tr><th>Служба</th><th>Состояние</th></tr></thead><tbody>
          ${unitsUi
            .map(
              (u) =>
                `<tr><td>${esc(u.label)}</td><td>${pill(u.ok, u.state)}</td></tr>`
            )
            .join("")}
        </tbody></table>
        <h3 class="section-title">Mango SIP</h3>
        <pre class="msg codeblock">${esc(s.registration_raw)}</pre>
        <h3 class="section-title">Пути</h3>
        <pre class="msg codeblock">${esc(JSON.stringify(s.paths || {}, null, 2))}</pre>
      </details>
    `;

    $("statusBox").querySelectorAll("[data-goto-context]").forEach((el) => {
      el.addEventListener("click", () => {
        openScenarioTools(
          el.getAttribute("data-goto-context") || "default",
          el.getAttribute("data-tool") || ""
        );
      });
    });

    $("statusBox").querySelectorAll("[data-goto-tab]").forEach((el) => {
      el.addEventListener("click", () => {
        setTab(el.getAttribute("data-goto-tab") || "status");
      });
    });

    $("statusBox").querySelectorAll(".call-row[data-call-id]").forEach((el) => {
      const open = () => {
        const id = el.getAttribute("data-call-id");
        if (!id) return;
        setTab("calls");
        openCall(id).catch((e) => alert(e.message));
      };
      el.addEventListener("click", open);
      el.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          open();
        }
      });
    });

    const btnOn = $("btnLineOn");
    const btnOff = $("btnLineOff");
    const lineMsg = $("lineMsg");
    async function toggleLine(next) {
      try {
        if (btnOn) btnOn.disabled = true;
        if (btnOff) btnOff.disabled = true;
        if (lineMsg) lineMsg.textContent = "Сохраняю…";
        const res = await setInboundLine(next);
        const st = (res && res.inbound_line) || {};
        if (lineMsg) {
          lineMsg.textContent =
            (res && res.message ? res.message + " · " : "") +
            "AstDB " +
            (st.astdb_path || "quantum/inbound_line") +
            " = " +
            (st.value || "");
        }
        await loadStatus();
      } catch (e) {
        if (lineMsg) lineMsg.textContent = e.message || String(e);
        alert(e.message || String(e));
      } finally {
        if (btnOn) btnOn.disabled = false;
        if (btnOff) btnOff.disabled = false;
      }
    }
    if (btnOn) btnOn.onclick = () => toggleLine(true);
    if (btnOff) btnOff.onclick = () => toggleLine(false);

    // Glance: pending dial list size
    const glance = $("campaignGlance");
    if (glance) {
      api("/api/campaign/preview?limit=1")
        .then((r) => {
          glance.innerHTML = `<p class="muted tight" style="margin-top:0.35rem">без пометки в Sheet: <b>${esc(
            r.total_pending ?? 0
          )}</b></p>`;
        })
        .catch(() => {
          glance.innerHTML = "";
        });
    }

    const pack = s.pack || [];
    if ($("packBox")) {
      $("packBox").innerHTML = `<table><thead><tr><th>Ключ</th><th>Путь</th><th></th><th>Заметка</th></tr></thead><tbody>
      ${pack
        .map(
          (p) =>
            `<tr><td>${esc(p.key)}</td><td><code>${esc(p.path)}</code></td><td>${pill(
              p.exists,
              p.exists ? "есть" : "нет"
            )}</td><td>${esc(p.note)}</td></tr>`
        )
        .join("")}
    </tbody></table>`;
    }
  }

  async function loadScenario(expandTool) {
    const ctx = ($("scContext") && $("scContext").value) || "default";
    await getToolsCatalog();
    const s = await api("/api/scenario?context=" + encodeURIComponent(ctx));
    $("scGreeting").value = s.greeting || "";
    $("scPrompt").value = s.prompt || "";
    $("scModel").value = s.model || "";
    $("scVoice").value = s.voice || "";
    $("scTemp").value = s.temperature ?? "";
    $("scProvider").value = s.provider || "";
    if ($("scIsolate")) {
      $("scIsolate").textContent =
        (s.profile_label ? "Профиль: " + s.profile_label + " · " : "") +
        "провайдер " +
        (s.provider || "?") +
        " · " +
        (s.note || "изолирован от другого направления");
    }
    const enabled = [...(s.tools || []), ...(s.post_call_tools || [])];
    renderScenarioTools(enabled, expandTool || "");
  }

  async function loadKnowledge() {
    const k = await api("/api/knowledge");
    $("knPath").textContent = `${k.path} · ${k.chars} chars · ${k.second_brain || ""}`;
    $("knText").value = k.text || "";
  }

  async function loadCalls() {
    const filter = ($("callsFilter") && $("callsFilter").value) || "";
    const q = filter ? `?limit=40&context=${encodeURIComponent(filter)}` : "?limit=40";
    const c = await api("/api/calls" + q);
    const rows = c.calls || [];
    $("callsBox").innerHTML = `<p class="muted">Всего: ${c.total}${
      filter ? " · фильтр " + esc(filter) : ""
    }. Время — Москва (МСК). Клик по строке — расшифровка.</p>
      <table class="calls-table"><thead><tr>
        <th>Когда (МСК)</th><th>Контекст</th><th>Кто</th><th>Длит.</th><th>Outcome</th><th>Сообщения</th>
      </tr></thead><tbody>
      ${rows
        .map(
          (r) => `<tr data-call-id="${esc(r.call_id)}" class="call-row" style="cursor:pointer">
        <td title="${esc(r.start_time || "")}">${esc(fmtMsk(r.start_time))}</td>
        <td><code>${esc(r.context_name || "")}</code></td>
        <td>${esc(r.caller_number)} ${esc(r.caller_name)}</td>
        <td>${esc(fmtDuration(r.duration_seconds))}</td>
        <td>${esc(r.outcome)}</td>
        <td class="preview">${esc(r.transcript_preview || "—")}</td>
      </tr>`
        )
        .join("")}
      </tbody></table>`;
    document.querySelectorAll(".call-row").forEach((tr) => {
      tr.onclick = () => openCall(tr.getAttribute("data-call-id"));
    });
  }

  async function openCall(callId) {
    if (!callId) return;
    const box = $("callDetail");
    box.innerHTML = "<p class='muted'>загрузка…</p>";
    try {
      const d = await api("/api/calls/" + encodeURIComponent(callId));
      const call = d.call || {};
      const turns = call.turns || [];
      const userTurns = turns.filter((t) => String(t.role || "").toLowerCase() === "user").length;
      const meta =
        `<div class="call-meta">` +
        `<div><b>call_id</b> <code>${esc(call.call_id || "")}</code></div>` +
        `<div><b>контекст</b> <code>${esc(call.context_name || "")}</code></div>` +
        `<div><b>номер</b> ${esc(call.caller_number || "")} ${esc(call.caller_name || "")}</div>` +
        `<div><b>время (МСК)</b> ${esc(fmtMsk(call.start_time))} → ${esc(
          fmtMsk(call.end_time)
        )} · ${esc(fmtDuration(call.duration_seconds))}</div>` +
        `<div><b>outcome</b> ${esc(call.outcome || "")}</div>` +
        `<div><b>реплики</b> всего ${turns.length} · клиент ${userTurns}</div>` +
        `</div>`;
      if (!turns.length) {
        box.innerHTML = meta + "<p class='muted'>Нет сообщений в расшифровке</p>";
        return;
      }
      const hint =
        userTurns === 0
          ? `<p class="muted">Реплик клиента нет — либо молчание/недозвон, либо ASR не распознал речь.</p>`
          : "";
      const table =
        `<table class="transcript-table"><thead><tr><th>#</th><th>Кто</th><th>Сообщение</th></tr></thead><tbody>` +
        turns
          .map((t) => {
            const role = String(t.role || "").toLowerCase();
            const who = esc(t.who || t.role || "");
            const cls = role === "user" ? "turn-user" : role === "assistant" ? "turn-ava" : "";
            return (
              `<tr class="${cls}"><td>${t.n ?? ""}</td><td>${who}</td>` +
              `<td>${esc(t.text || "")}</td></tr>`
            );
          })
          .join("") +
        `</tbody></table>`;
      box.innerHTML = meta + hint + table;
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (e) {
      box.textContent = e.message;
    }
  }

  function openCallFromCampaign(callId) {
    if (!callId) return;
    setTab("calls");
    openCall(callId).catch((e) => alert(e.message));
  }

  async function loadSecrets() {
    const s = await api("/api/secrets-checklist");
    $("secretsBox").innerHTML = `<table><thead><tr><th>Scope</th><th>Key</th><th></th><th>Hint</th></tr></thead><tbody>
      ${(s.items || [])
        .map(
          (i) =>
            `<tr><td>${esc(i.scope)}</td><td><code>${esc(i.key)}</code></td><td>${pill(
              i.present,
              i.present ? "ok" : "missing"
            )}</td><td>${esc(i.hint)}</td></tr>`
        )
        .join("")}
    </tbody></table>`;
  }

  async function refreshAll() {
    const errors = [];
    try {
      await loadStatus();
    } catch (e) {
      if ($("statusBox")) $("statusBox").textContent = e.message;
      errors.push(e);
    }
    const jobs = [
      ["scenario", loadScenario],
      ["knowledge", loadKnowledge],
      ["calls", loadCalls],
      ["secrets", loadSecrets],
      ["tools", loadDialTools],
    ];
    await Promise.all(
      jobs.map(async ([name, fn]) => {
        try {
          await fn();
        } catch (e) {
          errors.push(new Error(`${name}: ${e.message || e}`));
        }
      })
    );
    if (errors.length && !($("statusBox") && $("statusBox").querySelector(".status-grid"))) {
      // status itself failed — already shown
      return;
    }
    if (errors.length) {
      console.warn("refresh partial errors", errors.map((e) => e.message));
    }
  }

  let campPollTimer = null;

  function setCampActionMsg(text, ok) {
    const el = $("campActionMsg");
    if (!el) return;
    el.textContent = text || "";
    el.className = "msg " + (ok === true ? "ok" : ok === false ? "bad" : "");
  }

  function renderCampaignRunStatus(st) {
    const box = $("campRunBanner");
    if (!box) return;
    const running = !!(st && st.running);
    const msg = (st && st.message) || "—";
    const processed = (st && st.processed) || 0;
    const queued = (st && st.queued) || 0;
    const errors = (st && st.errors) || 0;
    const interrupted = !!(st && (st.interrupted || String(msg).includes("interrupted")));
    const last = (st && st.last) || {};
    const lastPhone = last.phone || "";
    const lastNote = last.note || "";
    const finished = st && st.finished_at ? fmtMsk(st.finished_at) : "";
    box.className =
      "camp-run-banner " + (running ? "running" : interrupted ? "warn" : "idle");
    box.innerHTML = running
      ? `<div class="run-title">● Обзвон идёт по очереди</div>
         <div>${esc(msg)}</div>
         <div class="muted">Сделано: ${processed}${queued ? " / " + queued : ""} · ошибок: ${errors}${
           lastPhone ? " · последний: " + esc(lastPhone) : ""
         }${lastNote ? " — " + esc(lastNote) : ""}</div>`
      : `<div class="run-title">${
          interrupted ? "⚠ Обзвон прерван" : "○ Обзвон не запущен"
        }</div>
         <div class="muted">${esc(
           msg === "idle" || !msg
             ? "Нажмите «Старт обзвона» — звонки сверху вниз, пометка после каждого"
             : msg
         )}</div>
         <div class="muted">Сделано в прошлом прогоне: ${processed} · ошибок: ${errors}${
           lastPhone ? " · последний: " + esc(lastPhone) : ""
         }${finished ? " · окончание: " + esc(finished) + " МСК" : ""}</div>`;
    if ($("btnCampStart")) $("btnCampStart").disabled = running;
    renderWritebackStatus(st);
  }

  function renderWritebackStatus(st) {
    const box = $("campWriteBanner");
    if (!box) return;
    const enabled = !!(st && st.sheets_write_enabled);
    const mode = (st && st.write_mode) || "off";
    const email = (st && st.sa_email) || "";
    box.className = "camp-run-banner " + (enabled ? "idle" : "warn");
    box.innerHTML = enabled
      ? `<div class="run-title">✓ Пометки пишутся в Sheet</div>
         <div class="muted">режим: ${esc(mode)}${email ? " · " + esc(email) : ""}</div>`
      : `<div class="run-title">⚠ Пометки пока только локально</div>
         <div class="muted">Вставьте Google Service Account JSON ниже и расшарьте таблицу на его email — тогда «Пометки Клиента» будут обновляться после каждого звонка.</div>`;
  }

  async function loadWritebackStatus() {
    try {
      const st = await api("/api/campaign/writeback");
      renderWritebackStatus(st);
      return st;
    } catch (e) {
      if ($("campWriteBanner")) {
        $("campWriteBanner").textContent = "Writeback: " + e.message;
        $("campWriteBanner").className = "camp-run-banner warn";
      }
    }
  }

  async function loadCampaignRunStatus() {
    const st = await api("/api/campaign/status");
    renderCampaignRunStatus(st);
    return st;
  }

  function startCampPolling() {
    stopCampPolling();
    campPollTimer = setInterval(() => {
      loadCampaignRunStatus().catch(() => {});
    }, 3000);
  }

  function stopCampPolling() {
    if (campPollTimer) {
      clearInterval(campPollTimer);
      campPollTimer = null;
    }
  }

  async function loadCampaignLeads() {
    const limit = Number(($("campLimit") && $("campLimit").value) || 50);
    const r = await api("/api/campaign/preview?limit=" + encodeURIComponent(limit));
    const items = r.items || [];
    const by = r.by_sheet || {};
    if ($("campLeadsMeta")) {
      const skipped = r.skipped_local_done || 0;
      $("campLeadsMeta").textContent =
        "В очереди на звонок: " +
        (r.total_pending ?? items.length) +
        " · показано " +
        (r.showing ?? items.length) +
        (skipped
          ? " · уже обработано локально (пропуск): " + skipped
          : "") +
        (r.sheets_write_enabled
          ? " · writeback Sheets: да"
          : " · writeback Sheets: нет — очередь двигается по локальной БД");
    }
    if ($("campSheetLink") && r.sheet_url) {
      $("campSheetLink").href = r.sheet_url;
      $("campSheetLink").hidden = false;
    }
    if ($("campStats")) {
      const cards = [
        ["В очереди", r.total_pending ?? 0],
        ...Object.entries(by).map(([name, n]) => [name, n]),
      ];
      $("campStats").innerHTML = cards
        .map(
          ([label, n]) =>
            `<div class="status-card ok"><span class="label">${esc(label)}</span><span class="value">${esc(
              n
            )}</span></div>`
        )
        .join("");
    }
    if ($("campLeadsBox")) {
      if (!items.length) {
        $("campLeadsBox").innerHTML =
          "<p class='muted'>Нет номеров без пометки — очередь пуста или Sheet недоступен.</p>";
      } else {
        $("campLeadsBox").innerHTML = `<table class="calls-table"><thead><tr>
          <th>#</th><th>Телефон</th><th>Лист</th><th>Строка</th><th>Дата</th><th>Источник</th>
        </tr></thead><tbody>
        ${items
          .map(
            (it, i) => `<tr>
          <td>${i + 1}</td>
          <td><code>${esc(it.phone)}</code></td>
          <td>${esc(it.sheet)}</td>
          <td>${esc(it.row)}</td>
          <td>${esc(it.date || "")}</td>
          <td class="preview">${esc(it.source || "")}</td>
        </tr>`
          )
          .join("")}
        </tbody></table>`;
      }
    }
    return r;
  }

  async function loadCampaignResults() {
    const box = $("campResultsBox");
    if (!box) return;
    try {
      const r = await api("/api/campaign/results?limit=40");
      const items = r.items || [];
      if (!items.length) {
        box.innerHTML = `<p class="muted">Пока нет локальных результатов (total=${r.total || 0})</p>`;
        return r;
      }
      box.innerHTML = `<p class="muted">Наша БД · всего: ${r.total} · показаны последние ${items.length}</p>
        <table class="calls-table"><thead><tr>
          <th>Когда (МСК)</th><th>Телефон</th><th>Пометка</th><th>Статус</th><th>Расшифровка</th><th>Sheet</th>
        </tr></thead><tbody>
        ${items
          .map((it) => {
            const tr = String(it.transcript || "").trim();
            const preview = tr
              ? esc(tr.length > 180 ? tr.slice(0, 179) + "…" : tr)
              : "<span class='muted'>—</span>";
            const openBtn = it.call_id
              ? `<button type="button" class="linkish" data-open-call="${esc(
                  it.call_id
                )}">открыть в Звонках</button>`
              : "";
            return `<tr>
          <td title="${esc(it.created_at || "")}">${esc(fmtMsk(it.created_at))}</td>
          <td><code>${esc(it.phone)}</code><div class="muted">${esc(it.sheet_name || "")} #${esc(
              it.row_number
            )}</div></td>
          <td class="preview">${esc(it.note || "")}</td>
          <td><b>${esc(it.status || "—")}</b></td>
          <td class="preview camp-transcript">${preview}${
              openBtn ? "<div>" + openBtn + "</div>" : ""
            }</td>
          <td>${pill(!!it.written, it.written ? "да" : "нет")}</td>
        </tr>`;
          })
          .join("")}
        </tbody></table>`;
      box.querySelectorAll("[data-open-call]").forEach((btn) => {
        btn.onclick = (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          openCallFromCampaign(btn.getAttribute("data-open-call"));
        };
      });
      return r;
    } catch (e) {
      box.innerHTML = `<p class="bad">${esc(e.message)}</p>`;
    }
  }

  async function loadCampaignPanel() {
    await Promise.all([
      loadCampaignScript().catch((e) => {
        if ($("campMsg")) {
          $("campMsg").textContent = e.message;
          $("campMsg").className = "msg bad";
        }
      }),
      loadCampaignLeads().catch((e) => {
        if ($("campLeadsBox")) {
          $("campLeadsBox").innerHTML = `<p class="bad">${esc(e.message)}</p>`;
        }
      }),
      loadCampaignResults(),
      loadCampaignRunStatus().catch((e) => {
        if ($("campRunBanner")) {
          $("campRunBanner").textContent = "Статус: " + e.message;
          $("campRunBanner").className = "camp-run-banner";
        }
      }),
      loadWritebackStatus(),
    ]);
    startCampPolling();
  }

  async function loadCampaignScript() {
    const r = await api("/api/campaign/script");
    if ($("campGreeting")) $("campGreeting").value = r.greeting || "";
    if ($("campScript")) $("campScript").value = r.script || "";
    if ($("campTools")) {
      $("campTools").textContent =
        "tools: " +
        ((r.tools || []).join(", ") || "—") +
        " · source=" +
        (r.source || "?") +
        (r.path ? " · " + r.path : "");
    }
    if ($("campMeta")) {
      $("campMeta").textContent =
        "Источник: " + (r.source || "?") + (r.path ? " (" + r.path + ")" : "");
    }
    return r;
  }

  function setTab(name) {
    document.querySelectorAll(".side-nav button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    const btn = document.querySelector(`.side-nav button[data-tab="${name}"]`);
    if (btn) btn.classList.add("active");
    const panel = $("tab-" + name);
    if (panel) panel.classList.add("active");
    const meta = TAB_META[name] || { title: name, hint: "" };
    if ($("pageTitle")) $("pageTitle").textContent = meta.title;
    if ($("pageHint")) $("pageHint").textContent = meta.hint;
    if (name === "campaign") {
      loadCampaignPanel();
    } else {
      stopCampPolling();
    }
    if (name === "outreach") {
      const frame = $("outreachFrame");
      const status = $("outreachLoadStatus");
      if (frame && !frame.getAttribute("src")) {
        if (status) {
          status.hidden = false;
          status.textContent = "Загрузка Outreach…";
        }
        frame.onload = () => {
          if (status) status.hidden = true;
        };
        frame.onerror = () => {
          if (status) {
            status.hidden = false;
            status.textContent = "Не удалось загрузить Outreach UI";
          }
        };
        frame.src = BASE + "/assets/outreach/index.html?v=scrollfix7";
      }
    }
  }

  if ($("btnCampLoad")) {
    $("btnCampLoad").onclick = () =>
      loadCampaignScript()
        .then(() => {
          $("campMsg").textContent = "загружено";
          $("campMsg").className = "msg ok";
        })
        .catch((e) => {
          $("campMsg").textContent = e.message;
          $("campMsg").className = "msg bad";
        });
  }
  if ($("btnCampSave")) {
    $("btnCampSave").onclick = async () => {
      try {
        const r = await api("/api/campaign/script", {
          method: "PUT",
          body: JSON.stringify({
            greeting: ($("campGreeting") && $("campGreeting").value) || "",
            script: ($("campScript") && $("campScript").value) || "",
          }),
        });
        $("campMsg").textContent = "сохранено (" + (r.source || "file") + ")";
        $("campMsg").className = "msg ok";
        await loadCampaignScript();
      } catch (e) {
        $("campMsg").textContent = e.message;
        $("campMsg").className = "msg bad";
      }
    };
  }
  if ($("btnCampReset")) {
    $("btnCampReset").onclick = async () => {
      try {
        await api("/api/campaign/script/reset", { method: "POST", body: "{}" });
        await loadCampaignScript();
        $("campMsg").textContent = "сброшено к builtin";
        $("campMsg").className = "msg ok";
      } catch (e) {
        $("campMsg").textContent = e.message;
        $("campMsg").className = "msg bad";
      }
    };
  }
  if ($("btnCampPreview")) {
    $("btnCampPreview").onclick = async () => {
      try {
        await loadCampaignLeads();
        await loadCampaignResults();
      } catch (e) {
        if ($("campLeadsBox")) $("campLeadsBox").innerHTML = `<p class="bad">${esc(e.message)}</p>`;
      }
    };
  }
  if ($("campLimit")) {
    $("campLimit").onchange = () =>
      loadCampaignLeads().catch((e) => {
        if ($("campLeadsBox")) $("campLeadsBox").innerHTML = `<p class="bad">${esc(e.message)}</p>`;
      });
  }
  if ($("btnCampStart")) {
    $("btnCampStart").onclick = async () => {
      const maxCalls = Number(($("campMax") && $("campMax").value) || 3);
      const dry = !!($("campDry") && $("campDry").checked);
      const label = dry
        ? `Запустить тест (dry_run) на ${maxCalls} номеров? Звонков не будет.`
        : `Запустить обзвон ${maxCalls} номеров из очереди?`;
      if (!confirm(label)) return;
      setCampActionMsg("Запуск…", null);
      try {
        const r = await api("/api/campaign/start", {
          method: "POST",
          body: JSON.stringify({ max_calls: maxCalls, dry_run: dry }),
        });
        if (r && r.ok === false) {
          const why =
            r.error === "already_running"
              ? "Обзвон уже идёт — смотрите статус выше. Сначала Стоп, потом снова Старт."
              : r.error || "не удалось запустить";
          setCampActionMsg(why, false);
          if (r.status) renderCampaignRunStatus(r.status);
          return;
        }
        setCampActionMsg(r.message || "Обзвон запущен", true);
        await loadCampaignRunStatus();
        await loadCampaignResults();
        startCampPolling();
      } catch (e) {
        setCampActionMsg(e.message, false);
      }
    };
  }
  if ($("btnCampStop")) {
    $("btnCampStop").onclick = async () => {
      setCampActionMsg("Остановка…", null);
      try {
        const r = await api("/api/campaign/stop", { method: "POST", body: "{}" });
        setCampActionMsg(r.message || "Остановка запрошена", true);
        await loadCampaignRunStatus();
      } catch (e) {
        setCampActionMsg(e.message, false);
      }
    };
  }
  if ($("btnCampFlush")) {
    $("btnCampFlush").onclick = async () => {
      setCampActionMsg("Дописываю пометки в Sheet…", null);
      try {
        const r = await api("/api/campaign/flush-writebacks", { method: "POST", body: "{}" });
        setCampActionMsg(
          r.ok === false
            ? r.error || "writeback недоступен"
            : `Дописано в Sheet: ${r.flushed || 0}`,
          r.ok !== false && (r.flushed || 0) >= 0
        );
        await loadCampaignResults();
        await loadWritebackStatus();
      } catch (e) {
        setCampActionMsg(e.message, false);
      }
    };
  }
  if ($("btnCampSaSave")) {
    $("btnCampSaSave").onclick = async () => {
      const raw = (($("campSaJson") && $("campSaJson").value) || "").trim();
      const msg = $("campSaMsg");
      if (!raw) {
        if (msg) {
          msg.textContent = "Вставьте JSON ключа";
          msg.className = "msg bad";
        }
        return;
      }
      let doc;
      try {
        doc = JSON.parse(raw);
      } catch (e) {
        if (msg) {
          msg.textContent = "Невалидный JSON";
          msg.className = "msg bad";
        }
        return;
      }
      if (msg) {
        msg.textContent = "Сохраняю…";
        msg.className = "msg";
      }
      try {
        const r = await api("/api/campaign/google-sa", {
          method: "POST",
          body: JSON.stringify({ json: doc }),
        });
        if (msg) {
          msg.textContent =
            "OK · " +
            (r.sa_email || "") +
            (r.share_hint ? " · " + r.share_hint : "") +
            (r.flush ? ` · flush=${r.flush.flushed || 0}` : "");
          msg.className = "msg ok";
        }
        if ($("campSaJson")) $("campSaJson").value = "";
        await loadWritebackStatus();
        await loadCampaignResults();
      } catch (e) {
        if (msg) {
          msg.textContent = e.message;
          msg.className = "msg bad";
        }
      }
    };
  }

  document.querySelectorAll(".side-nav button").forEach((btn) => {
    btn.addEventListener("click", () => setTab(btn.dataset.tab));
  });

  window.addEventListener("message", (ev) => {
    const data = ev && ev.data;
    if (!data || data.type !== "quantum-console") return;
    if (data.action === "open-outbound") {
      setTab("outbound");
      if (data.phone && $("dialPhone")) $("dialPhone").value = String(data.phone);
      if (data.contact && $("dialContact")) $("dialContact").value = String(data.contact);
      if (data.company && $("dialCompany")) $("dialCompany").value = String(data.company);
      if (data.topic && $("dialTopic")) $("dialTopic").value = String(data.topic);
    }
  });

  if ($("loginForm")) $("loginForm").addEventListener("submit", doLogin);
  if ($("btnLogout")) $("btnLogout").onclick = () => doLogout();
  if ($("btnRefresh")) {
    $("btnRefresh").onclick = () => refreshAll().catch((e) => alert(e.message));
  }
  if ($("btnLoadScenario")) {
    $("btnLoadScenario").onclick = () => loadScenario().catch((e) => alert(e.message));
  }
  if ($("scContext")) {
    $("scContext").onchange = () => loadScenario().catch((e) => alert(e.message));
  }
  if ($("btnReloadCalls")) {
    $("btnReloadCalls").onclick = () => loadCalls().catch((e) => alert(e.message));
  }
  if ($("callsFilter")) {
    $("callsFilter").onchange = () => loadCalls().catch((e) => alert(e.message));
  }

  if ($("btnSaveScenario")) {
    $("btnSaveScenario").onclick = async () => {
      try {
        const tools = selectedScenarioTools();
        const r = await api("/api/scenario", {
          method: "PUT",
          body: JSON.stringify({
            context: ($("scContext") && $("scContext").value) || "default",
            greeting: $("scGreeting").value,
            prompt: $("scPrompt").value,
            model: $("scModel").value,
            voice: $("scVoice").value,
            temperature: $("scTemp").value === "" ? null : Number($("scTemp").value),
            provider: $("scProvider").value,
            tools,
            restart: true,
          }),
        });
        $("scMsg").textContent =
          (r.note || "сохранено") +
          (r.isolated_from ? ` · не тронут: ${r.isolated_from}` : " · AI engine перезапущен");
        $("scMsg").className = "msg ok";
        toolsCatalogCache = null;
        await loadScenario();
      } catch (e) {
        $("scMsg").textContent = e.message;
        $("scMsg").className = "msg bad";
      }
    };
  }

  if ($("btnRestartEngine")) {
    $("btnRestartEngine").onclick = async () => {
      try {
        const r = await api("/api/actions/restart-engine", { method: "POST" });
        $("scMsg").textContent = r.ok ? "ai_engine restarted" : r.output || "fail";
      } catch (e) {
        $("scMsg").textContent = e.message;
      }
    };
  }

  if ($("btnSaveKnowledge")) {
    $("btnSaveKnowledge").onclick = async () => {
      try {
        const r = await api("/api/knowledge", {
          method: "PUT",
          body: JSON.stringify({ text: $("knText").value, reload: true }),
        });
        const rel = r.knowledge_reload || {};
        $("knMsg").textContent =
          rel.ok === false
            ? `saved, reload fail: ${rel.error || "?"}`
            : "knowledge сохранена + Second Brain reload";
        $("knMsg").className = "msg ok";
      } catch (e) {
        $("knMsg").textContent = e.message;
        $("knMsg").className = "msg bad";
      }
    };
  }

  const TOOL_GROUP_RU = {
    http: "Офис и знания",
    business: "Встречи и почта",
    telephony: "Телефония",
    other: "Прочее",
  };

  const TOOL_HINT_RU = {
    get_company_knowledge: "Подтянуть факт из базы знаний компании",
    hangup_call: "Завершить разговор",
    check_calendar: "Проверить свободные слоты в календаре",
    create_calendar_event: "Создать встречу в календаре",
    create_conference: "Создать ссылку Телемост",
    send_email: "Отправить письмо",
    send_welcome_email: "Отправить welcome / презентацию",
    leave_voicemail: "Оставить голосовое на автоответчик",
    live_agent_transfer: "Перевести на живого сотрудника",
    send_email_summary: "Отправить краткое резюме звонка",
    request_transcript: "Запросить текст разговора во время звонка",
  };

  /** Tools shown by default; rest under «ещё». */
  const TOOL_PRIMARY = new Set([
    "get_company_knowledge",
    "hangup_call",
    "check_calendar",
    "create_calendar_event",
    "create_conference",
    "send_email",
    "send_welcome_email",
  ]);

  function dialMode() {
    const el = document.querySelector('input[name="dialMode"]:checked');
    return el ? el.value : "custom";
  }

  function syncDialModeUI() {
    const mode = dialMode();
    const kb = $("dialKnowledgeBlock");
    if (kb) kb.hidden = mode !== "knowledge";
    const kbTool = document.querySelector('input.dial-tool[value="get_company_knowledge"]');
    if (kbTool) {
      kbTool.checked = mode === "knowledge";
      kbTool.disabled = mode !== "knowledge";
    }
  }

  function composeCallTask() {
    const contact = (($("dialContact") && $("dialContact").value) || "").trim();
    const behalf = (($("dialBehalf") && $("dialBehalf").value) || "").trim();
    const company = (($("dialCompany") && $("dialCompany").value) || "").trim();
    const topic = (($("dialTopic") && $("dialTopic").value) || "").trim();
    const goal = (($("dialGoal") && $("dialGoal").value) || "").trim();
    const notes = (($("dialNotes") && $("dialNotes").value) || "").trim();
    const mode = dialMode();
    const kbSel = $("dialKbTopic");
    const kbTitle =
      kbSel && kbSel.value
        ? (kbSel.options[kbSel.selectedIndex] || {}).text || kbSel.value
        : "";

    if (!goal) {
      throw new Error("Укажите чёткое задание — что должен сделать робот");
    }

    const who = contact || "собеседник";
    let greeting = (($("dialGreeting") && $("dialGreeting").value) || "").trim();
    if (!greeting) {
      const from = behalf || "Quantum Labs";
      greeting = contact
        ? `Алло, ${contact}? Это ${from}. Удобно полминуты?`
        : `Алло, это ${from}. Удобно полминуты?`;
    }

    const lines = [];
    lines.push("Ты — голосовой секретарь Quantum Labs. Говори коротко, по-русски, по делу.");
    lines.push("");
    lines.push("КОНТЕКСТ ЗВОНКА:");
    lines.push(`- Собеседник: ${who}${company ? ` (${company})` : ""}`);
    if (behalf) lines.push(`- Звонишь от имени: ${behalf}`);
    if (topic) lines.push(`- Тема: ${topic}`);
    if (mode === "knowledge") {
      lines.push(
        kbTitle && kbTitle.indexOf("выберите") < 0
          ? `- Источник фактов: база знаний компании (тема «${kbTitle}»).`
          : "- Источник фактов: база знаний компании — вызывай get_company_knowledge, если не хватает цифр/фактов."
      );
      lines.push("- Не уходи в чужие темы базы, если они не нужны для ЭТОГО задания.");
    } else {
      lines.push("- Источник фактов: ТОЛЬКО это задание. Базу знаний компании НЕ используй и tool get_company_knowledge НЕ вызывай.");
    }
    lines.push("");
    lines.push("ЗАДАНИЕ (главное):");
    lines.push(goal);
    if (notes) {
      lines.push("");
      lines.push("ДОП. УКАЗАНИЯ:");
      lines.push(notes);
    }
    lines.push("");
    lines.push("КАК ВЕСТИ РАЗГОВОР:");
    lines.push("1) Представься и уточни, удобно ли говорить.");
    lines.push("2) Выполни задание выше. Не выдумывай факты.");
    lines.push("3) Если собеседник отказался — вежливо попрощайся.");
    lines.push("4) В конце кратко подтверди договорённость или ответ.");
    lines.push("5) hangup_call только после ясного завершения или отказа, не в первые секунды.");

    return { greeting, script: lines.join("\n"), use_knowledge: mode === "knowledge", goal };
  }

  async function loadKbTopics() {
    const sel = $("dialKbTopic");
    if (!sel) return;
    try {
      const r = await api("/api/knowledge/topics");
      const topics = r.topics || [];
      const cur = sel.value;
      sel.innerHTML =
        '<option value="">— любая по заданию —</option>' +
        topics
          .map(
            (t) =>
              `<option value="${esc(t.id)}">${esc(t.title || t.id)}</option>`
          )
          .join("");
      if (cur) sel.value = cur;
    } catch {
      /* topics optional */
    }
  }

  async function loadDialTools() {
    const box = $("dialTools");
    if (!box) return;
    try {
      const r = await api("/api/tools");
      const dialable = new Set(r.dialable || []);
      const tools = (r.tools || []).filter((t) => dialable.has(t.name));
      const byGroup = {};
      tools.forEach((t) => {
        const g = t.group || "other";
        (byGroup[g] = byGroup[g] || []).push(t);
      });
      const order = ["http", "business", "telephony", "other"];
      const keys = [
        ...order.filter((k) => byGroup[k]),
        ...Object.keys(byGroup).filter((k) => !order.includes(k)),
      ];

      function toolRow(t, checked) {
        const hint = TOOL_HINT_RU[t.name] || t.description || "";
        return `<label class="tool-item" title="${esc(hint)}">
          <input type="checkbox" class="dial-tool" value="${esc(t.name)}" ${
            checked ? "checked" : ""
          } />
          <span class="tool-item-text">
            <span class="tool-item-label">${esc(t.label || t.name)}</span>
            <span class="tool-item-hint">${esc(hint)}</span>
          </span>
        </label>`;
      }

      const primary = [];
      const extra = [];
      keys.forEach((g) => {
        byGroup[g].forEach((t) => {
          if (TOOL_PRIMARY.has(t.name)) primary.push({ g, t });
          else extra.push({ g, t });
        });
      });

      const renderGroup = (items) => {
        const groups = {};
        items.forEach(({ g, t }) => {
          (groups[g] = groups[g] || []).push(t);
        });
        return Object.keys(groups)
          .map((g) => {
            const title = TOOL_GROUP_RU[g] || g;
            const rows = groups[g]
              .map((t) =>
                toolRow(
                  t,
                  t.name === "hangup_call" ||
                    (t.name === "get_company_knowledge" && dialMode() === "knowledge")
                )
              )
              .join("");
            return `<div class="tool-group"><div class="tool-group-title">${esc(
              title
            )}</div>${rows}</div>`;
          })
          .join("");
      };

      box.innerHTML =
        renderGroup(primary) +
        (extra.length
          ? `<details class="task-advanced"><summary>Ещё возможности</summary>${renderGroup(
              extra
            )}</details>`
          : "");

      syncDialModeUI();
      document.querySelectorAll('input[name="dialMode"]').forEach((el) => {
        el.onchange = () => {
          syncDialModeUI();
          // rebuild script hint if empty goal already composed
        };
      });
    } catch (e) {
      box.innerHTML = `<span class="muted">Не удалось загрузить возможности: ${esc(
        e.message
      )}</span>`;
    }
    await loadKbTopics();
  }

  function selectedDialTools() {
    return Array.from(document.querySelectorAll("input.dial-tool:checked"))
      .filter((el) => !el.disabled)
      .map((el) => el.value);
  }

  function showDialMsg(text, ok) {
    const el = $("dialMsg");
    if (!el) return;
    el.hidden = false;
    el.textContent = text;
    el.className = ok === true ? "msg ok codeblock" : ok === false ? "msg bad codeblock" : "msg codeblock";
  }

  if ($("btnComposeTask")) {
    $("btnComposeTask").onclick = () => {
      try {
        const c = composeCallTask();
        if ($("dialGreeting")) $("dialGreeting").value = c.greeting;
        if ($("dialScript")) $("dialScript").value = c.script;
        const det = $("dialScriptDetails");
        if (det) det.open = true;
        showDialMsg("Сценарий собран. Можно править и звонить.", true);
      } catch (e) {
        showDialMsg(e.message, false);
      }
    };
  }

  if ($("btnCallback")) {
    $("btnCallback").onclick = async () => {
      try {
        showDialMsg("Запрос через Mango…");
        const r = await api("/api/outbound/callback", {
          method: "POST",
          body: JSON.stringify({ phone: $("dialPhone").value }),
        });
        showDialMsg(JSON.stringify(r, null, 2), !!r.ok);
      } catch (e) {
        showDialMsg(e.message, false);
      }
    };
  }

  if ($("btnDial")) {
    $("btnDial").onclick = async () => {
      try {
        const phone = (($("dialPhone") && $("dialPhone").value) || "").trim();
        if (!phone) throw new Error("Укажите телефон");

        let greeting = (($("dialGreeting") && $("dialGreeting").value) || "").trim();
        let script = (($("dialScript") && $("dialScript").value) || "").trim();
        const composed = composeCallTask();
        if (!greeting) greeting = composed.greeting;
        if (!script) script = composed.script;
        if ($("dialGreeting") && !$("dialGreeting").value.trim()) {
          $("dialGreeting").value = greeting;
        }
        if ($("dialScript") && !$("dialScript").value.trim()) {
          $("dialScript").value = script;
        }

        const tools = selectedDialTools();
        // Ensure knowledge tool matches mode
        const useKnowledge = dialMode() === "knowledge";
        const toolSet = new Set(tools);
        if (useKnowledge) toolSet.add("get_company_knowledge");
        else toolSet.delete("get_company_knowledge");
        if (!toolSet.has("hangup_call")) toolSet.add("hangup_call");

        showDialMsg("Звоним…");
        const payload = {
          phone,
          context: "outbound",
          greeting,
          script,
          use_knowledge: useKnowledge,
          tools: Array.from(toolSet),
        };
        const r = await api("/api/outbound/dial", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        showDialMsg(
          r.ok
            ? `Звонок запущен на ${r.phone || phone}. Смотрите вкладку «Звонки».\n` +
                JSON.stringify(
                  {
                    channel_id: r.channel_id,
                    state: r.state,
                    use_knowledge: useKnowledge,
                    script_chars: r.script_chars,
                  },
                  null,
                  2
                )
            : JSON.stringify(r, null, 2),
          !!r.ok
        );
      } catch (e) {
        showDialMsg(e.message, false);
      }
    };
  }

  if ($("btnBackup")) {
    $("btnBackup").onclick = async () => {
      try {
        $("packMsg").textContent = "backup…";
        const r = await api("/api/actions/backup", { method: "POST" });
        $("packMsg").textContent = JSON.stringify(r, null, 2);
      } catch (e) {
        $("packMsg").textContent = e.message;
      }
    };
  }
  if ($("btnReloadDp")) {
    $("btnReloadDp").onclick = async () => {
      try {
        const r = await api("/api/actions/reload-dialplan", { method: "POST" });
        $("packMsg").textContent = JSON.stringify(r, null, 2);
      } catch (e) {
        $("packMsg").textContent = e.message;
      }
    };
  }

  (async () => {
    const ok = await checkAuth();
    if (ok) {
      try {
        await refreshAll();
      } catch (e) {
        if ($("statusBox")) $("statusBox").textContent = e.message;
      }
    }
  })();
})();
