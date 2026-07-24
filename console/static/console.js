(() => {
  const $ = (id) => document.getElementById(id);
  const BASE =
    typeof window !== "undefined" && window.__QC_BASE__
      ? String(window.__QC_BASE__)
      : location.pathname.startsWith("/_quantum_console")
        ? "/_quantum_console"
        : "";

  const TAB_META = {
    status: { title: "Статус", hint: "Сервисы, SIP и пути на хосте" },
    scenario: { title: "Сценарий", hint: "YAML-профили входящих и исходящих" },
    knowledge: { title: "База знаний", hint: "Second Brain · quantum_labs.md" },
    calls: { title: "Звонки", hint: "История и расшифровки" },
    campaign: { title: "Кампания Sheets", hint: "Скрипт массового обзвона из Google Sheet" },
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
    }. Клик по строке — расшифровка.</p>
      <table class="calls-table"><thead><tr>
        <th>Когда</th><th>Контекст</th><th>Кто</th><th>Сек</th><th>Outcome</th><th>Сообщения</th>
      </tr></thead><tbody>
      ${rows
        .map(
          (r) => `<tr data-call-id="${esc(r.call_id)}" class="call-row" style="cursor:pointer">
        <td>${esc(r.start_time)}</td>
        <td><code>${esc(r.context_name || "")}</code></td>
        <td>${esc(r.caller_number)} ${esc(r.caller_name)}</td>
        <td>${r.duration_seconds ?? ""}</td>
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
      const meta =
        `<div class="call-meta">` +
        `<div><b>call_id</b> <code>${esc(call.call_id || "")}</code></div>` +
        `<div><b>контекст</b> <code>${esc(call.context_name || "")}</code></div>` +
        `<div><b>номер</b> ${esc(call.caller_number || "")} ${esc(call.caller_name || "")}</div>` +
        `<div><b>время</b> ${esc(call.start_time || "")} → ${esc(call.end_time || "")} · ${
          call.duration_seconds ?? "?"
        }с</div>` +
        `<div><b>outcome</b> ${esc(call.outcome || "")}</div>` +
        `</div>`;
      if (!turns.length) {
        box.innerHTML = meta + "<p class='muted'>Нет сообщений в расшифровке</p>";
        return;
      }
      const table =
        `<table class="transcript-table"><thead><tr><th>#</th><th>Кто</th><th>Сообщение</th></tr></thead><tbody>` +
        turns
          .map(
            (t) =>
              `<tr><td>${t.n ?? ""}</td><td>${esc(t.who || t.role || "")}</td>` +
              `<td>${esc(t.text || "")}</td></tr>`
          )
          .join("") +
        `</tbody></table>`;
      box.innerHTML = meta + table;
    } catch (e) {
      box.textContent = e.message;
    }
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
    await loadStatus();
    await Promise.all([
      loadScenario(),
      loadKnowledge(),
      loadCalls(),
      loadSecrets(),
      loadDialTools(),
    ]);
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
      loadCampaignScript().catch((e) => {
        if ($("campMsg")) {
          $("campMsg").textContent = e.message;
          $("campMsg").className = "msg bad";
        }
      });
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
        const r = await api("/api/campaign/preview?limit=15");
        $("campOut").textContent = JSON.stringify(r, null, 2);
      } catch (e) {
        $("campOut").textContent = e.message;
      }
    };
  }
  if ($("btnCampStart")) {
    $("btnCampStart").onclick = async () => {
      try {
        const r = await api("/api/campaign/start", {
          method: "POST",
          body: JSON.stringify({
            max_calls: Number(($("campMax") && $("campMax").value) || 3),
            dry_run: !!($("campDry") && $("campDry").checked),
          }),
        });
        $("campOut").textContent = JSON.stringify(r, null, 2);
      } catch (e) {
        $("campOut").textContent = e.message;
      }
    };
  }
  if ($("btnCampStop")) {
    $("btnCampStop").onclick = async () => {
      try {
        const r = await api("/api/campaign/stop", { method: "POST", body: "{}" });
        $("campOut").textContent = JSON.stringify(r, null, 2);
      } catch (e) {
        $("campOut").textContent = e.message;
      }
    };
  }
  if ($("btnCampStatus")) {
    $("btnCampStatus").onclick = async () => {
      try {
        const r = await api("/api/campaign/status");
        $("campOut").textContent = JSON.stringify(r, null, 2);
      } catch (e) {
        $("campOut").textContent = e.message;
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
