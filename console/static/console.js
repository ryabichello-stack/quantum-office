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
    status: { title: "Обзор", hint: "Сервисы и здоровье системы" },
    outreach: { title: "Outreach", hint: "Bitrix, очередь писем, ответы, anti-ban" },
    scenario: { title: "Сценарий", hint: "YAML-профили входящих и исходящих" },
    knowledge: { title: "База знаний", hint: "Second Brain · quantum_labs.md" },
    calls: { title: "Звонки", hint: "История и расшифровки" },
    campaign: { title: "Обзвон Sheets", hint: "База номеров из Google Sheet и скрипт кампании" },
    outbound: { title: "Исходящий", hint: "Один звонок с per-call сценарием" },
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

  async function loadStatus() {
    const s = await api("/api/status");
    const services = s.services || [];
    const unitsUi = s.units_ui || [];
    const profiles = s.profiles || {};
    const sipOk = !!s.mango_registered;

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
        : `<span class="muted">нет tools</span>`;
      return `<div class="profile-card">
        <h3>${esc(p.label || key)}</h3>
        <div>${chips}</div>
        <div class="actions" style="margin-top:0.65rem">
          <button type="button" data-goto-context="${esc(
            p.context || ""
          )}">Настроить tools</button>
        </div>
      </div>`;
    }

    $("statusBox").innerHTML = `
      <div class="status-head">
        <div>
          <div class="status-host">${esc(s.host_label || "Quantum Labs · телефония")}</div>
          <p class="host-note">${esc(s.host_note || "")}</p>
        </div>
        <div>${pill(sipOk, sipOk ? "SIP на связи" : "SIP не зарегистрирован")}</div>
      </div>
      <div class="status-grid">
        ${services
          .map(
            (svc) =>
              `<div class="status-card ${svc.ok ? "ok" : "bad"}" title="${esc(svc.hint || "")}">
                <span class="label">${esc(svc.label || svc.id)}</span>
                <span class="value">${svc.ok ? "работает" : "недоступен"}</span>
              </div>`
          )
          .join("")}
      </div>
      <h2 class="section-title">Инструменты в профилях</h2>
      <p class="muted">Клик по tool или «Настроить» — детали и включение в сценарии</p>
      <div class="profile-tools">
        ${profileCard("inbound")}
        ${profileCard("outbound")}
      </div>
      <div id="campaignGlance" class="profile-tools"></div>
      <h2 class="section-title">Службы systemd</h2>
      <table><thead><tr><th>Служба</th><th>Состояние</th></tr></thead><tbody>
        ${unitsUi
          .map(
            (u) =>
              `<tr><td>${esc(u.label)}</td><td>${pill(u.ok, u.state)}</td></tr>`
          )
          .join("")}
      </tbody></table>
      <h2 class="section-title">Регистрация Mango</h2>
      <pre class="msg codeblock">${esc(s.registration_raw)}</pre>
      <h2 class="section-title">Пути</h2>
      <pre class="msg codeblock">${esc(JSON.stringify(s.paths || {}, null, 2))}</pre>
    `;

    $("statusBox").querySelectorAll("[data-goto-context]").forEach((el) => {
      el.addEventListener("click", () => {
        openScenarioTools(
          el.getAttribute("data-goto-context") || "default",
          el.getAttribute("data-tool") || ""
        );
      });
    });

    // Glance: pending dial list size
    const glance = $("campaignGlance");
    if (glance) {
      api("/api/campaign/preview?limit=1")
        .then((r) => {
          glance.innerHTML = `<div class="profile-card">
            <h3>Обзвон Sheets</h3>
            <p class="muted">В очереди без пометки: <b>${esc(r.total_pending ?? 0)}</b></p>
            <div class="actions" style="margin-top:0.55rem">
              <button type="button" id="btnGotoCampaign">Открыть базу</button>
            </div>
          </div>`;
          const b = $("btnGotoCampaign");
          if (b) b.onclick = () => setTab("campaign");
        })
        .catch(() => {
          glance.innerHTML = "";
        });
    }

    const pack = s.pack || [];
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
    const last = (st && st.last) || {};
    const lastPhone = last.phone || "";
    const lastNote = last.note || "";
    box.className = "camp-run-banner " + (running ? "running" : "idle");
    box.innerHTML = running
      ? `<div class="run-title">● Обзвон идёт</div>
         <div>${esc(msg)}</div>
         <div class="muted">Сделано: ${processed}${queued ? " / " + queued : ""} · ошибок: ${errors}${
           lastPhone ? " · последний: " + esc(lastPhone) : ""
         }${lastNote ? " — " + esc(lastNote) : ""}</div>`
      : `<div class="run-title">○ Обзвон не запущен</div>
         <div class="muted">${esc(msg === "idle" || !msg ? "Нажмите «Старт обзвона», чтобы начать звонки из очереди" : msg)}</div>
         <div class="muted">Сделано в прошлом прогоне: ${processed} · ошибок: ${errors}${
           lastPhone ? " · последний: " + esc(lastPhone) : ""
         }</div>`;
    if ($("btnCampStart")) $("btnCampStart").disabled = running;
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
      box.innerHTML = `<p class="muted">Всего в БД: ${r.total} · показаны последние ${items.length}</p>
        <table class="calls-table"><thead><tr>
          <th>Когда</th><th>Телефон</th><th>Лист</th><th>Пометка</th><th>Расшифровка</th><th>В Sheet</th>
        </tr></thead><tbody>
        ${items
          .map((it) => {
            const tr = String(it.transcript || "").trim();
            const preview = tr
              ? esc(tr.length > 220 ? tr.slice(0, 219) + "…" : tr)
              : "<span class='muted'>—</span>";
            const openBtn = it.call_id
              ? `<button type="button" class="linkish" data-open-call="${esc(
                  it.call_id
                )}">открыть в Звонках</button>`
              : "";
            return `<tr>
          <td>${esc(it.created_at || "")}</td>
          <td><code>${esc(it.phone)}</code></td>
          <td>${esc(it.sheet_name || "")} #${esc(it.row_number)}</td>
          <td class="preview">${esc(it.note || "")}<div class="muted">${esc(
              it.status || it.interest || ""
            )}</div></td>
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
        frame.src = BASE + "/assets/outreach/index.html";
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

  document.querySelectorAll(".side-nav button").forEach((btn) => {
    btn.addEventListener("click", () => setTab(btn.dataset.tab));
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

  async function loadDialTools() {
    const box = $("dialTools");
    if (!box) return;
    try {
      const r = await api("/api/tools");
      const dialable = new Set(r.dialable || []);
      const tools = (r.tools || []).filter((t) => dialable.has(t.name));
      const groups = {};
      tools.forEach((t) => {
        const g = t.group || "other";
        (groups[g] = groups[g] || []).push(t);
      });
      const order = ["http", "telephony", "business", "other"];
      const keys = [
        ...order.filter((k) => groups[k]),
        ...Object.keys(groups).filter((k) => !order.includes(k)),
      ];
      box.innerHTML = keys
        .map((g) => {
          const items = groups[g]
            .map(
              (t) =>
                `<label class="check"><input type="checkbox" class="dial-tool" value="${esc(
                  t.name
                )}" data-name="${esc(t.name)}" /> ${esc(t.label || t.name)} <code>${esc(
                  t.name
                )}</code></label>`
            )
            .join("");
          return `<div class="full"><strong>${esc(g)}</strong></div>${items}`;
        })
        .join("");
      const kb = box.querySelector('input.dial-tool[value="get_company_knowledge"]');
      const uk = $("dialUseKnowledge");
      if (kb && uk) {
        uk.onchange = () => {
          kb.checked = uk.checked;
        };
        kb.onchange = () => {
          uk.checked = kb.checked;
        };
      }
    } catch (e) {
      box.innerHTML = `<span class="muted">tools: ${esc(e.message)}</span>`;
    }
  }

  function selectedDialTools() {
    return Array.from(document.querySelectorAll("input.dial-tool:checked")).map((el) => el.value);
  }

  if ($("btnCallback")) {
    $("btnCallback").onclick = async () => {
      try {
        $("dialMsg").textContent = "Mango API callback…";
        const r = await api("/api/outbound/callback", {
          method: "POST",
          body: JSON.stringify({ phone: $("dialPhone").value }),
        });
        $("dialMsg").textContent = JSON.stringify(r, null, 2);
        $("dialMsg").className = r.ok ? "msg ok codeblock" : "msg bad codeblock";
      } catch (e) {
        $("dialMsg").textContent = e.message;
        $("dialMsg").className = "msg bad codeblock";
      }
    };
  }

  if ($("btnDial")) {
    $("btnDial").onclick = async () => {
      try {
        $("dialMsg").textContent = "SIP originate (per-call script)…";
        const greeting = (($("dialGreeting") && $("dialGreeting").value) || "").trim();
        const script = (($("dialScript") && $("dialScript").value) || "").trim();
        const tools = selectedDialTools();
        const payload = {
          phone: $("dialPhone").value,
          context: ($("dialContext") && $("dialContext").value) || "outbound",
          use_knowledge: !!($("dialUseKnowledge") && $("dialUseKnowledge").checked),
        };
        if (greeting) payload.greeting = greeting;
        if (script) payload.script = script;
        if (tools.length) payload.tools = tools;
        const r = await api("/api/outbound/dial", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        $("dialMsg").textContent = JSON.stringify(r, null, 2);
        $("dialMsg").className = r.ok ? "msg ok codeblock" : "msg bad codeblock";
      } catch (e) {
        $("dialMsg").textContent = e.message;
        $("dialMsg").className = "msg bad codeblock";
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
