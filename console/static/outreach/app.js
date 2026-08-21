(() => {
  const titles = {
    letter: "Кампания",
    dash: "Рассылка",
    outbox: "Очередь",
    replies: "Ответы",
    inbox: "Входящие",
    clients: "Клиенты",
    report: "Отчёт",
    settings: "Настройки",
  };
  const hints = {
    letter: "Отрасль, письмо, цепочка и презентация",
    dash: "Старт рассылки, тест себе и пачка из очереди",
    outbox: "Кого отправим следующим",
    replies: "Ответы на отправленные письма",
    inbox: "Классификация входящих",
    clients: "База Bitrix и обогащение",
    report: "Воронка доставки и чтения",
    settings: "Лимиты, окно часов и защита ящика",
  };

  function apiBase() {
    if (typeof window !== "undefined" && window.__QC_OUTREACH_API__) {
      return String(window.__QC_OUTREACH_API__);
    }
    const m = location.pathname.match(/^(.*)\/ui\/?$/);
    if (m) return m[1];
    const m2 = location.pathname.match(/^(.*)\/ui\//);
    return m2 ? m2[1] : "";
  }
  const BASE = apiBase();
  const EMBEDDED = !!(typeof window !== "undefined" && window.__QC_OUTREACH_EMBEDDED__);

  let token = EMBEDDED ? "" : localStorage.getItem("outreach_token") || "";
  let settingsCache = null;

  const $ = (id) => document.getElementById(id);

  async function api(path, opts = {}) {
    const isForm = typeof FormData !== "undefined" && opts.body instanceof FormData;
    const headers = Object.assign(
      isForm ? {} : { "Content-Type": "application/json" },
      opts.headers || {},
      !EMBEDDED && token ? { "X-Outreach-Token": token } : {}
    );
    const res = await fetch(BASE + path, {
      ...opts,
      headers,
      credentials: "same-origin",
    });
    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      data = { detail: await res.text() };
    }
    if (res.status === 401) {
      if (EMBEDDED) {
        $("loginError") && ($("loginError").textContent = "Сессия консоли истекла — обновите страницу и войдите снова");
        showLogin();
      } else {
        showLogin();
      }
      throw new Error("Нужна авторизация");
    }
    if (!res.ok) {
      const detail = data && (data.detail || data.error);
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || data));
    }
    return data;
  }

  function setLogoPreview(url) {
    const img = $("letterLogoPreview");
    const meta = $("letterLogoMeta");
    if (!img) return;
    const src = (url || "").trim();
    if (src) {
      img.src = src;
      img.hidden = false;
    } else {
      img.removeAttribute("src");
      img.hidden = true;
    }
    if (meta) meta.textContent = src ? src.replace(/^https?:\/\//, "").slice(0, 64) : "нет логотипа";
  }

  function campaignPreviewPayload() {
    return {
      contact_name: "Иван",
      subject: $("letterSubject").value,
      plain: $("letterPlain").value,
      html: $("letterHtml").value,
      company_name: $("letterCompany").value,
      website: $("letterWebsite").value,
      phone: $("letterPhone").value,
      contact_email: $("letterEmail") ? $("letterEmail").value : "",
      signature: $("letterSignature") ? $("letterSignature").value : "",
      logo_url: ($("letterLogoPreview") && $("letterLogoPreview").getAttribute("src")) || "",
      logo_enabled: $("letterLogoEnabled") ? $("letterLogoEnabled").checked : true,
    };
  }

  function cleanSigLines(text) {
    const lines = String(text || "").split("\n").map((ln) => ln.replace(/\s+$/g, ""));
    const out = [];
    for (const ln of lines) {
      if (!ln.trim() && out.length && !out[out.length - 1].trim()) continue;
      out.push(ln);
    }
    while (out.length && !out[0].trim()) out.shift();
    while (out.length && !out[out.length - 1].trim()) out.pop();
    return out.join("\n");
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function contactIconUrl(name) {
    // Through Console proxy when embedded; absolute outreach path otherwise.
    if (BASE) return BASE.replace(/\/$/, "") + "/assets/brand/icons/" + name + ".png";
    return "https://a.47z.ru/_ava_outreach/assets/brand/icons/" + name + ".png";
  }

  function bindContactIcons() {
    document.querySelectorAll(".contact-icon[data-icon]").forEach((img) => {
      const name = img.getAttribute("data-icon");
      if (name) img.src = contactIconUrl(name);
    });
  }

  function normalizeSignatureTemplate(tpl) {
    const drop = new Set([
      "{website}",
      "{email}",
      "{email_line}",
      "{phone}",
      "{phone_line}",
      "{website}{phone_line}",
      "{website}{email_line}",
      "{website}{email_line}{phone_line}",
    ]);
    const lines = String(tpl || "")
      .replace(/\r\n/g, "\n")
      .split("\n")
      .filter((ln) => {
        const s = ln.trim();
        if (!s) return true;
        if (drop.has(s)) return false;
        if (s.startsWith("{") && s.endsWith("}") && /(website|email|phone)/.test(s)) return false;
        return true;
      });
    const cleaned = cleanSigLines(lines.join("\n"));
    return cleaned || "С уважением,\nкоманда Quantum Labs\n{company}";
  }

  function refreshSignatureLive() {
    // Contacts are edited in the icon fields themselves — no duplicate read-only block.
    bindContactIcons();
  }

  function campaignContactPayload() {
    const sigEl = $("letterSignature");
    if (sigEl) sigEl.value = normalizeSignatureTemplate(sigEl.value);
    return {
      OUTREACH_COMPANY_NAME: ($("letterCompany") && $("letterCompany").value) || "",
      OUTREACH_WEBSITE: ($("letterWebsite") && $("letterWebsite").value) || "",
      OUTREACH_CONTACT_PHONE: ($("letterPhone") && $("letterPhone").value) || "",
      OUTREACH_CONTACT_EMAIL: ($("letterEmail") && $("letterEmail").value) || "",
      OUTREACH_SIGNATURE: (sigEl && sigEl.value) || "",
      OUTREACH_LOGO_URL: ($("letterLogoPreview") && $("letterLogoPreview").getAttribute("src")) || "",
      OUTREACH_LOGO_ENABLED: $("letterLogoEnabled") && $("letterLogoEnabled").checked ? "true" : "false",
    };
  }

  async function applyCampaignContacts(opts = {}) {
    const quiet = !!opts.quiet;
    refreshSignatureLive();
    const data = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ settings: campaignContactPayload() }),
    });
    settingsCache = data.settings || settingsCache;
    if (!quiet && $("letterLog")) {
      $("letterLog").hidden = false;
      const phone = (($("letterPhone") && $("letterPhone").value) || "").trim();
      $("letterLog").textContent = phone
        ? `Контакты применены. В подписи: ${phone}`
        : "Контакты применены (телефон пустой — строка Телефон не попадёт в письмо).";
    }
    return data;
  }

  function showLogin() {
    $("login").classList.remove("hidden");
    $("app").classList.add("hidden");
  }

  function showApp() {
    $("login").classList.add("hidden");
    $("app").classList.remove("hidden");
  }

  function logAction(obj) {
    $("actionLog").textContent =
      typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  }

  function setRunStateBadge(state) {
    const el = $("runStateBadge");
    const st = (state || "stopped").toLowerCase();
    const labels = { playing: "Идёт", paused: "Пауза", stopped: "Стоп" };
    el.textContent = labels[st] || st;
    el.className = "badge " + (st in labels ? st : "stopped");
    const banner = $("runBanner");
    if (banner) {
      banner.className = "run-banner " + (st in labels ? st : "stopped");
      const title = $("runBannerTitle");
      const text = $("runBannerText");
      if (st === "playing") {
        if (title) title.textContent = "Рассылка идёт";
        if (text) text.textContent = "Можно отправлять пачки из очереди. Пауза — временно остановить, Стоп — выключить.";
      } else if (st === "paused") {
        if (title) title.textContent = "На паузе";
        if (text) text.textContent = "Массовая отправка приостановлена. Нажмите «Старт», чтобы продолжить.";
      } else {
        if (title) title.textContent = "Рассылка остановлена";
        if (text) text.textContent = "Нажмите «Старт», чтобы разрешить массовую отправку из очереди.";
      }
    }
  }

  let packsCache = [];
  let selectedPackId = "";

  function requestParentCall(payload) {
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage(
          Object.assign({ type: "quantum-console", action: "open-outbound" }, payload || {}),
          "*"
        );
      }
    } catch (_) {}
  }

  function renderPackCards(activeId) {
    const box = $("packCards");
    if (!box) return;
    if (!packsCache.length) {
      box.innerHTML = `<p class="muted">Пакеты не загружены</p>`;
      return;
    }
    box.innerHTML = packsCache
      .map((p) => {
        const on = p.id === activeId ? "active" : "";
        return `<label class="pack-card ${on}">
          <input type="radio" name="packId" value="${escapeHtml(p.id)}" ${p.id === activeId ? "checked" : ""} />
          <span>
            <strong>${escapeHtml(p.title)}</strong>
            <small>${escapeHtml(p.short || "")}</small>
            <em>${escapeHtml(p.audience || "")} · ${p.steps || 3} письма</em>
          </span>
        </label>`;
      })
      .join("");
    box.querySelectorAll('input[name="packId"]').forEach((inp) => {
      inp.addEventListener("change", () => {
        selectedPackId = inp.value;
        previewPack(selectedPackId);
        box.querySelectorAll(".pack-card").forEach((c) => c.classList.remove("active"));
        inp.closest(".pack-card")?.classList.add("active");
      });
    });
  }

  async function loadPacks() {
    try {
      const data = await api("/api/packs");
      packsCache = data.items || [];
      const active = (settingsCache && settingsCache.OUTREACH_SEQUENCE_PACK) || selectedPackId || "lombards";
      selectedPackId = active;
      renderPackCards(active);
      if (active) await previewPack(active, false);
    } catch (err) {
      if ($("packCards")) $("packCards").textContent = String(err.message || err);
    }
  }

  async function previewPack(packId, fillEditors = true) {
    if (!packId) return;
    const data = await api("/api/packs/" + encodeURIComponent(packId));
    const pack = data.pack || {};
    selectedPackId = pack.pack_id || packId;
    if ($("packActiveMeta")) {
      $("packActiveMeta").textContent =
        `Выбрано: ${pack.title || packId} — ${pack.short || ""}`;
    }
    if ($("packStepsPreview")) {
      $("packStepsPreview").innerHTML = (pack.steps || [])
        .map(
          (s) =>
            `<li><strong>День ${s.delay_days}</strong> · ${escapeHtml(s.label || "")}: ${escapeHtml(
              s.subject || ""
            )}${s.attach_presentation ? " · PDF" : ""}</li>`
        )
        .join("");
    }
    if ($("letterPdfMeta")) {
      $("letterPdfMeta").textContent = pack.presentation
        ? `Файл презентации: ${pack.presentation}`
        : "";
    }
    if (fillEditors) {
      if (pack.subject) $("letterSubject").value = pack.subject;
      if (pack.plain) $("letterPlain").value = pack.plain;
      if (pack.html) $("letterHtml").value = pack.html;
      if ($("letterAttachPdf")) {
        $("letterAttachPdf").checked = !!pack.attach_presentation_default;
      }
      ["letterPlain", "letterHtml", "letterSignature"].forEach((id) => autoGrowField($(id)));
    }
    return pack;
  }

  function setEnabledBadge(on) {
    // legacy no-op kept for older calls — mirror into run badge if needed
    if (typeof on === "boolean") {
      /* ignore */
    }
  }

  function renderStats(dash) {
    const c = (dash.outbox && dash.outbox.counts) || {};
    const e = dash.engagement || {};
    const items = [
      ["Очередь", c.pending || 0],
      ["Отправлено", e.sent || c.sent || 0],
      ["Доставлено≈", e.delivered ?? "—"],
      ["Открыто", e.opened || 0],
      ["Не открыто", e.not_opened || 0],
      ["Bounce", e.bounced || c.bounced || 0],
      ["Ответы", e.replied || c.replied || 0],
      ["Сегодня", dash.outbox ? dash.outbox.sent_today : 0],
    ];
    $("statGrid").innerHTML = items
      .map(
        ([l, n]) =>
          `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`
      )
      .join("");

    const daily = dash.daily || [];
    const max = Math.max(1, ...daily.map((d) => d.sent || 0));
    $("dailyChart").innerHTML = daily.length
      ? daily
          .map((d) => {
            const pct = Math.round(((d.sent || 0) / max) * 100);
            return `<div class="bar-row"><span>${d.day}</span><div class="bar"><span style="width:${pct}%"></span></div><span>${d.sent}</span></div>`;
          })
          .join("")
      : `<p class="muted">Пока нет отправок</p>`;
  }

  async function loadDash() {
    const dash = await api("/api/dashboard");
    renderStats(dash);
    setRunStateBadge(dash.run_state || (dash.runner && dash.runner.state) || "stopped");
  }

  function fmtPct(v) {
    if (v === null || v === undefined) return "—";
    return `${v}%`;
  }

  function engBadge(eng) {
    const map = {
      sent: ["sent", "Отправлено"],
      opened: ["opened", "Открыто"],
      bounced: ["bounced", "Bounce"],
      replied: ["replied", "Ответ"],
    };
    const [cls, label] = map[eng] || ["sent", eng || "—"];
    return `<span class="eng ${cls}">${label}</span>`;
  }

  async function loadReport() {
    const days = Number($("reportDays").value || 14);
    const data = await api(`/api/modules/analytics/report?days=${days}&recent_limit=50`);
    const f = data.funnel || {};
    const r = data.rates || {};
    $("reportMeta").textContent =
      `Сгенерировано ${data.generated_at || "—"} · open tracking: ${
        data.open_tracking ? "вкл" : "выкл"
      } · base ${data.tracking_public_base || ""}`;

    const funnelCards = [
      ["В очереди", f.queued || 0],
      ["Отправлено", f.sent || 0],
      ["Доставлено≈", f.delivered || 0],
      ["Не доставлено", f.not_delivered || 0],
      ["Открыто", f.opened || 0],
      ["Не открыто", f.not_opened || 0],
      ["Ответы", f.replied || 0],
      ["Failed SMTP", f.failed || 0],
    ];
    $("reportFunnel").innerHTML = funnelCards
      .map(([l, n]) => `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`)
      .join("");

    $("reportRates").innerHTML = [
      ["Доставка", fmtPct(r.delivery_rate_pct)],
      ["Bounce", fmtPct(r.bounce_rate_pct)],
      ["Открытия", fmtPct(r.open_rate_pct)],
      ["Ответы", fmtPct(r.reply_rate_pct)],
      ["Ответ / открытие", fmtPct(r.reply_of_opened_pct)],
    ]
      .map(
        ([l, v]) =>
          `<div class="rate-card"><div class="n">${v}</div><div class="l">${l}</div></div>`
      )
      .join("") || `<div class="rate-card"><div class="n">—</div><div class="l">нет данных</div></div>`;

    const stages = [
      ["Отправлено", f.sent || 0],
      ["Доставлено≈", f.delivered || 0],
      ["Открыто", f.opened || 0],
      ["Ответ", f.replied || 0],
    ];
    const maxF = Math.max(1, ...stages.map(([, n]) => n));
    $("reportFunnelBars").innerHTML = stages
      .map(
        ([label, n]) =>
          `<div class="funnel-row"><span>${label}</span><div class="funnel-track"><i style="width:${
            (100 * n) / maxF
          }%"></i></div><b>${n}</b></div>`
      )
      .join("");

    const notes = (f.notes && Object.entries(f.notes)) || [];
    $("reportNotes").innerHTML = notes.length
      ? notes
          .map(([k, v]) => `<li><strong>${escapeHtml(k)}:</strong> ${escapeHtml(v)}</li>`)
          .join("")
      : `<li class="muted">Пока нет пояснений по воронке</li>`;

    const daily = data.daily || [];
    const maxD = Math.max(
      1,
      ...daily.map((d) => Math.max(d.sent || 0, d.opened || 0, d.bounced || 0, d.replied || 0))
    );
    $("reportDaily").innerHTML = daily.length
      ? daily
          .map((d) => {
            const sentH = Math.max(2, Math.round((40 * (d.sent || 0)) / maxD));
            const openH = Math.max(2, Math.round((40 * (d.opened || 0)) / maxD));
            return `<div class="bar-group" title="${d.day}: отправлено ${d.sent || 0}, открыто ${
              d.opened || 0
            }, bounce ${d.bounced || 0}, ответ ${d.replied || 0}">
          <div class="bar-stack">
            <div class="bar sent" style="height:${sentH}px"></div>
            <div class="bar open" style="height:${openH}px"></div>
          </div>
          <span>${String(d.day).slice(5)}</span>
        </div>`;
          })
          .join("")
      : `<p class="muted tight" style="padding:0.35rem 0">Нет отправок за период</p>`;

    $("reportRecent").innerHTML = (data.recent || [])
      .map(
        (row) => `<tr>
        <td>${engBadge(row.engagement)}</td>
        <td>${escapeHtml(row.email || "")}</td>
        <td>${escapeHtml(row.company || "")}</td>
        <td>${escapeHtml((row.subject || "").slice(0, 48))}</td>
        <td>${escapeHtml((row.created_at || "").slice(0, 16))}</td>
        <td>${row.opened_at ? escapeHtml(String(row.opened_at).slice(0, 16)) + (row.open_count > 1 ? ` ×${row.open_count}` : "") : "—"}</td>
        <td>${row.bounced_at ? escapeHtml((row.bounce_reason || "bounce").slice(0, 40)) : "—"}</td>
        <td>${row.replied_at ? escapeHtml(String(row.replied_at).slice(0, 16)) : "—"}</td>
      </tr>`
      )
      .join("");
  }

  async function loadSettingsIntoForms() {
    const data = await api("/api/settings");
    settingsCache = data.settings || {};
    const s = settingsCache;
    $("letterSubject").value = s.OUTREACH_SUBJECT || "";
    $("letterCompany").value = s.OUTREACH_COMPANY_NAME || "";
    $("letterWebsite").value = s.OUTREACH_WEBSITE || "";
    $("letterPhone").value = s.OUTREACH_CONTACT_PHONE || "";
    if ($("letterEmail")) {
      $("letterEmail").value =
        s.OUTREACH_CONTACT_EMAIL || s.OUTREACH_UNSUBSCRIBE_MAILTO || s.MAIL_USERNAME || "office@quantumlabs.ru";
    }
    if ($("letterSignature")) {
      $("letterSignature").value = normalizeSignatureTemplate(
        s.OUTREACH_SIGNATURE || "С уважением,\nкоманда Quantum Labs\n{company}"
      );
    }
    if ($("letterLogoEnabled")) {
      $("letterLogoEnabled").checked = String(s.OUTREACH_LOGO_ENABLED || "true").toLowerCase() !== "false";
    }
    setLogoPreview(s.OUTREACH_LOGO_URL || "");
    $("letterPlain").value = s.OUTREACH_TEMPLATE_PLAIN || "";
    $("letterHtml").value = s.OUTREACH_TEMPLATE_HTML || "";
    ["letterPlain", "letterHtml", "letterSignature"].forEach((id) => autoGrowField($(id)));

    $("schedEnabled").checked = String(s.SCHEDULE_ENABLED).toLowerCase() === "true" || s.SCHEDULE_ENABLED === "1";
    $("runRespectWindow").checked = String(s.RUN_RESPECT_WINDOW || "true").toLowerCase() !== "false";
    $("schedStart").value = s.SCHEDULE_WINDOW_START || 10;
    $("schedEnd").value = s.SCHEDULE_WINDOW_END || 18;
    $("schedTz").value = s.SCHEDULE_TIMEZONE || "Europe/Moscow";
    $("schedBatch").value = s.SCHEDULE_BATCH_SIZE || 1;
    $("schedTick").value = s.SCHEDULE_TICK_SECONDS || 300;

    $("setEnabled").checked = String(s.OUTREACH_ENABLED).toLowerCase() === "true" || s.OUTREACH_ENABLED === "1";
    setRunStateBadge(s.OUTREACH_RUN_STATE || "stopped");
    $("setDaily").value = s.OUTREACH_DAILY_LIMIT || 20;
    $("setDelayMin").value = s.OUTREACH_DELAY_MIN_SECONDS || 60;
    $("setDelayMax").value = s.OUTREACH_DELAY_MAX_SECONDS || 180;
    $("setDeal").checked = String(s.BITRIX_CREATE_DEAL || "true").toLowerCase() !== "false";
    $("setAssigned").value = s.BITRIX_ASSIGNED_BY_ID || 1;
    $("setStage").value = s.BITRIX_DEAL_STAGE_ID || "NEW";
    $("setReplyWatch").checked = String(s.REPLY_WATCH_ENABLED || "true").toLowerCase() !== "false";
    $("settingsMeta").textContent = `SMTP: ${s.MAIL_USERNAME || "—"} · Bitrix webhook: ${
      s.BITRIX_WEBHOOK_CONFIGURED ? "да" : "нет"
    } · portal ${s.BITRIX_PORTAL_URL || ""}`;
    setEnabledBadge($("setEnabled").checked);

    $("warmupEnabled").checked = String(s.WARMUP_ENABLED || "true").toLowerCase() !== "false";
    $("domainCap").value = s.DOMAIN_DAILY_CAP || 2;
    $("plusReply").checked = String(s.TRACKING_PLUS_REPLY_TO || "false").toLowerCase() === "true" || s.TRACKING_PLUS_REPLY_TO === "1";
    $("openTracking").checked = String(s.OPEN_TRACKING_ENABLED || "true").toLowerCase() !== "false";
    if ($("letterAttachPdf")) {
      $("letterAttachPdf").checked =
        String(s.OUTREACH_ATTACH_PRESENTATION || "false").toLowerCase() === "true" ||
        s.OUTREACH_ATTACH_PRESENTATION === "1";
    }
    if ($("letterPdfMeta") && s.OUTREACH_PRESENTATION_PDF) {
      $("letterPdfMeta").textContent = `Файл презентации: ${s.OUTREACH_PRESENTATION_PDF}`;
    }
    selectedPackId = s.OUTREACH_SEQUENCE_PACK || selectedPackId || "";
    if (!$("oneTo").value && s.MAIL_USERNAME) {
      $("oneTo").value = s.MAIL_USERNAME;
    }
    refreshSignatureLive();
  }

  async function loadAntiban() {
    await loadSettingsIntoForms();
    const dash = await api("/api/dashboard");
    const d = dash.deliverability || {};
    const cards = [
      ["Warm-up день", d.warmup_day_index ?? "—"],
      ["Эфф. лимит", d.effective_daily_limit ?? "—"],
      ["Конфиг лимит", d.configured_daily_limit ?? "—"],
      ["Suppressed", d.suppressed ?? 0],
      ["Доменов сегодня", d.domains_touched_today ?? 0],
      ["Cap/домен", d.domain_daily_cap ?? 2],
    ];
    $("antibanStats").innerHTML = cards
      .map(([l, n]) => `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`)
      .join("");
    await loadSuppression();
    await loadEvents();
  }

  async function loadSuppression() {
    const data = await api("/api/modules/deliverability/suppression?limit=100");
    $("suppBody").innerHTML = (data.items || [])
      .map(
        (r) => `<tr>
        <td>${escapeHtml(r.email)}</td>
        <td>${escapeHtml(r.reason || "")}</td>
        <td>${escapeHtml(r.source || "")}</td>
        <td><button type="button" class="small ghost" data-supp="${escapeHtml(r.email)}">удалить</button></td>
      </tr>`
      )
      .join("");
  }

  async function loadEvents() {
    const data = await api("/api/modules/tracking/events?limit=40");
    $("eventsBody").innerHTML = (data.items || [])
      .map((r) => {
        let eng = "sent";
        if (r.replied_at) eng = "replied";
        else if (r.bounced_at) eng = "bounced";
        else if (r.opened_at) eng = "opened";
        return `<tr>
        <td>${r.id}</td>
        <td>${escapeHtml(r.email)}</td>
        <td>${engBadge(eng)}</td>
        <td>${r.opened_at ? escapeHtml(String(r.opened_at).slice(0, 16)) : "—"}</td>
        <td>${r.bounced_at ? "да" : "—"}</td>
        <td>${escapeHtml((r.message_id || "").slice(0, 36))}</td>
      </tr>`;
      })
      .join("");
  }

  async function loadClients() {
    const st = await api("/api/modules/clients/status");
    const c = st.counts || {};
    $("clientsStats").innerHTML = [
      ["Компании", c.companies || 0],
      ["Контакты", c.contacts || 0],
      ["Email", c.emails || 0],
      ["Реквизиты", c.requisites || 0],
      ["С ИНН", c.companies_with_inn || 0],
    ]
      .map(([l, n]) => `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`)
      .join("");
    const last = st.last_sync;
    if (last) {
      $("clientsLog").textContent = JSON.stringify(last.report || last, null, 2);
    }
    await loadDadataStatus();
    await loadClientsEmails();
  }

  async function loadDadataStatus() {
    try {
      const st = await api("/api/modules/dadata/status");
      $("dadataMeta").textContent = st.configured
        ? `DaData: ключ есть · кэш ${((st.counts || {}).cached) || 0} · с ФИО ${
            ((st.counts || {}).with_director) || 0
          } · Bitrix: записано ${st.bitrix_pushed ?? "—"} / ждёт ${st.bitrix_pending ?? "—"}`
        : "DaData: нет DADATA_API_KEY в /opt/ava-outreach/.env — lookup по API недоступен, кэш можно смотреть";
      renderDadataRows(st.recent || []);
    } catch (e) {
      $("dadataMeta").textContent = String(e);
    }
  }

  function renderDadataRows(items) {
    $("dadataBody").innerHTML = (items || [])
      .map(
        (r) => `<tr>
        <td>${escapeHtml(r.inn || "")}</td>
        <td>${escapeHtml(r.company_name || "")}</td>
        <td>${escapeHtml(r.director_name || "—")}</td>
        <td>${escapeHtml(r.director_post || "—")}</td>
        <td>${escapeHtml(r.okved || "—")}</td>
        <td>${escapeHtml((r.fetched_at || "").slice(0, 16))}</td>
      </tr>`
      )
      .join("");
  }

  async function dadataLookup(force) {
    const inn = ($("dadataInn").value || "").trim();
    if (!inn) {
      $("dadataLog").textContent = "Укажите ИНН";
      return;
    }
    const qs = new URLSearchParams({ inn, force: force ? "true" : "false" });
    const data = await api("/api/modules/dadata/lookup?" + qs.toString());
    $("dadataLog").textContent = JSON.stringify(data, null, 2);
    await loadDadataStatus();
  }

  async function loadClientsEmails() {
    const q = ($("clientsQ").value || "").trim();
    const qs = new URLSearchParams({ limit: "80", offset: "0" });
    if (q) qs.set("q", q);
    const data = await api("/api/modules/clients/emails?" + qs.toString());
    $("clientsBody").innerHTML = (data.items || [])
      .map(
        (r) => `<tr>
        <td>${escapeHtml(r.email || "")}</td>
        <td>${escapeHtml(r.display_name || "")}</td>
        <td>${escapeHtml(r.source || "")}</td>
        <td>${escapeHtml(r.bitrix_id || "")}</td>
        <td>${escapeHtml(r.company_bitrix_id || "")}</td>
      </tr>`
      )
      .join("");
  }

  async function loadOutbox() {
    const q = $("outboxQ").value.trim();
    const status = $("outboxStatus").value;
    const qs = new URLSearchParams({ limit: "80", offset: "0" });
    if (q) qs.set("q", q);
    if (status) qs.set("status", status);
    const data = await api("/api/outbox?" + qs.toString());
    $("outboxMeta").textContent = `Показано ${data.items.length} из ${data.total}`;
    $("outboxBody").innerHTML = data.items
      .map((r) => {
        const actions = ["pending", "skipped", "failed"]
          .map(
            (st) =>
              `<button type="button" class="small ghost" data-id="${r.id}" data-st="${st}">${st}</button>`
          )
          .join(" ");
        return `<tr>
          <td>${r.id}</td>
          <td>${escapeHtml(r.email)}</td>
          <td>${escapeHtml(r.contact_name || "")}</td>
          <td>${escapeHtml(r.status)}</td>
          <td>${escapeHtml(r.sent_at || "")}</td>
          <td>${escapeHtml(r.deal_id || "")}</td>
          <td>${actions}</td>
        </tr>`;
      })
      .join("");
  }

  async function loadReplies() {
    const data = await api("/api/replies?limit=80");
    $("repliesBody").innerHTML = data.items
      .map(
        (r) => `<tr>
        <td>${escapeHtml(r.created_at || "")}</td>
        <td>${escapeHtml(r.from_email || "")}</td>
        <td>${escapeHtml(r.subject || "")}</td>
        <td>${escapeHtml(r.deal_id || "")}</td>
      </tr>`
      )
      .join("");
  }

  async function loadInbox(unprocessedOnly = true) {
    const q = unprocessedOnly ? "unprocessed_only=true" : "unprocessed_only=false";
    const data = await api("/api/modules/replies/inbox?" + q + "&limit=80");
    const c = data.counts || {};
    $("inboxStats").innerHTML = `
      <div class="stat"><span>Всего</span><strong>${c.total || 0}</strong></div>
      <div class="stat"><span>Необработанные</span><strong>${c.unprocessed || 0}</strong></div>`;
    $("inboxBody").innerHTML = (data.items || [])
      .map((r) => {
        const btn =
          r.processed == 0
            ? `<button type="button" data-inbox-id="${r.id}">Готово</button>`
            : "";
        return `<tr>
          <td>${escapeHtml(r.created_at || "")}</td>
          <td>${escapeHtml(r.from_email || "")}</td>
          <td>${escapeHtml(r.classification || "")} (${Number(r.confidence || 0).toFixed(2)})</td>
          <td>${escapeHtml(r.subject || "")}</td>
          <td>${escapeHtml(r.company_id || "")}</td>
          <td>${btn}</td>
        </tr>`;
      })
      .join("");
  }

  function bindTabs() {
    document.querySelectorAll(".tabs button").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const tab = btn.dataset.tab;
        $("tab-" + tab).classList.add("active");
        $("pageTitle").textContent = titles[tab] || tab;
        if ($("pageHint")) $("pageHint").textContent = hints[tab] || "";
        if (tab === "clients") loadClients().catch((e) => ($("clientsLog").textContent = String(e)));
        if (tab === "outbox") loadOutbox().catch(logAction);
        if (tab === "replies") loadReplies().catch(logAction);
        if (tab === "report") loadReport().catch(logAction);
        if (tab === "settings") {
          loadSettingsIntoForms()
            .then(() => loadAntiban())
            .catch((e) => {
              if ($("antibanLog")) $("antibanLog").textContent = String(e);
              logAction(e);
            });
        }
        if (tab === "letter" || tab === "dash") {
          loadSettingsIntoForms()
            .then(() => (tab === "letter" ? loadPacks() : loadDash()))
            .catch(logAction);
        }
        if (tab === "inbox") loadInbox(true).catch(logAction);
      });
    });
  }

  function paintPreviewHtml(box, html) {
    if (!box) return;
    const raw = String(html || "").trim();
    if (!raw) {
      box.innerHTML =
        "<p style='margin:0;color:#5a6b78;font:14px/1.45 Manrope,Segoe UI,sans-serif'>Нет HTML-версии — нажмите «Превью» ещё раз или примените отрасль.</p>";
      return;
    }
    // Never assign a full <html> document via innerHTML — browsers drop it and the
    // white preview looks empty while the dark plain pane still works.
    let inner = raw;
    const bodyMatch = raw.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
    if (bodyMatch) inner = bodyMatch[1];
    inner = inner
      .replace(/<!DOCTYPE[^>]*>/gi, "")
      .replace(/<\/?(html|head)[^>]*>/gi, "")
      .replace(/<meta[^>]*>/gi, "")
      .trim();
    if (!inner) {
      box.innerHTML =
        "<p style='margin:0;color:#5a6b78;font:14px/1.45 Manrope,Segoe UI,sans-serif'>HTML пустой после разбора шаблона.</p>";
      return;
    }
    box.innerHTML =
      "<div class='email-preview-root' style='color:#1a1a1a;font:14px/1.5 Manrope,Segoe UI,Helvetica,Arial,sans-serif;background:#fff'>" +
      inner +
      "</div>";
  }

  function autoGrowField(el) {
    if (!el || el.tagName !== "TEXTAREA") return;
    const maxPx = Math.min(window.innerHeight * 0.7, 560);
    el.style.height = "auto";
    const next = Math.min(Math.max(el.scrollHeight + 2, 120), maxPx);
    el.style.height = next + "px";
    el.style.overflowY = el.scrollHeight + 2 > maxPx ? "auto" : "hidden";
  }

  function bindCampaignFieldScroll() {
    const fields = ["letterPlain", "letterHtml", "letterSignature"]
      .map((id) => $(id))
      .filter(Boolean);
    fields.forEach((el) => {
      autoGrowField(el);
      el.addEventListener("input", () => autoGrowField(el));
    });

    // Wheel inside capped textareas / preview: scroll the element under the cursor.
    // Capture + preventDefault only when we actually move scrollTop — otherwise the
    // Console parent page eats the gesture and the field looks "stuck".
    if (document.documentElement.dataset.qlWheel === "1") return;
    document.documentElement.dataset.qlWheel = "1";
    document.addEventListener(
      "wheel",
      (ev) => {
        const t = ev.target;
        if (!t || !t.closest) return;
        const el = t.closest("textarea, pre.log, .preview-html");
        if (!el) return;
        // Preview is an iframe — let its document handle wheel natively
        if (el.tagName === "IFRAME") return;
        if (Math.abs(ev.deltaY) < Math.abs(ev.deltaX)) return;

        const max = el.scrollHeight - el.clientHeight;
        if (max <= 1) {
          // Field fully grown / short — scroll the iframe page instead
          const root = document.scrollingElement || document.documentElement;
          const rootMax = root.scrollHeight - root.clientHeight;
          if (rootMax <= 1) return;
          let dy = ev.deltaY;
          if (ev.deltaMode === 1) dy *= 20;
          else if (ev.deltaMode === 2) dy *= root.clientHeight;
          const before = root.scrollTop;
          root.scrollTop = Math.max(0, Math.min(rootMax, before + dy));
          if (root.scrollTop !== before) {
            ev.preventDefault();
            ev.stopPropagation();
          }
          return;
        }

        let dy = ev.deltaY;
        if (ev.deltaMode === 1) dy *= 20;
        else if (ev.deltaMode === 2) dy *= el.clientHeight;
        const before = el.scrollTop;
        const next = Math.max(0, Math.min(max, before + dy));
        if (next === before) return;
        el.scrollTop = next;
        ev.preventDefault();
        ev.stopPropagation();
      },
      { passive: false, capture: true }
    );
  }

  function bindInnerWheelScroll() {
    bindCampaignFieldScroll();
    try {
      document.documentElement.style.overscrollBehaviorY = "contain";
      document.body.style.overscrollBehaviorY = "contain";
    } catch (_) {}
  }

  async function boot() {
    bindTabs();
    bindContactIcons();
    bindInnerWheelScroll();
    const adv = $("letterAdvanced");
    if (adv) {
      adv.addEventListener("toggle", () => {
        if (adv.open) bindInnerWheelScroll(adv);
      });
    }

    if ($("loginBtn") && $("tokenInput")) {
      $("loginBtn").addEventListener("click", async () => {
        $("loginError").textContent = "";
        const t = $("tokenInput").value.trim();
        try {
          await fetch(BASE + "/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ token: t }),
          }).then(async (res) => {
            if (!res.ok) throw new Error("Неверный токен");
          });
          token = t;
          localStorage.setItem("outreach_token", t);
          showApp();
          await loadDash();
          await loadSettingsIntoForms();
        } catch (e) {
          if ($("loginError")) $("loginError").textContent = e.message || String(e);
        }
      });
    }

    $("refreshBtn").addEventListener("click", () => {
      loadDash().catch(logAction);
    });

    async function runControl(action) {
      try {
        const data = await api("/api/modules/runner/" + action, { method: "POST", body: "{}" });
        setRunStateBadge(data.state);
        logAction(data);
        await loadDash();
      } catch (e) {
        logAction(String(e));
      }
    }
    $("runPlayBtn").addEventListener("click", () => {
      if (!confirm("Старт: начать или продолжить массовую отправку из очереди?")) return;
      runControl("play");
    });
    $("runPauseBtn").addEventListener("click", () => runControl("pause"));
    $("runStopBtn").addEventListener("click", () => {
      if (!confirm("Стоп: полностью остановить рассылку?")) return;
      runControl("stop");
    });

    if ($("gotoCampaignBtn")) {
      $("gotoCampaignBtn").addEventListener("click", () => {
        document.querySelector('.tabs button[data-tab="letter"]')?.click();
      });
    }
    if ($("gotoCallBtn")) {
      $("gotoCallBtn").addEventListener("click", () => requestParentCall({}));
    }

    $("syncBtn").addEventListener("click", async () => {
      try {
        logAction(await api("/sync", { method: "POST", body: "{}" }));
        await loadDash();
      } catch (e) {
        logAction(String(e));
      }
    });
    $("clientsSyncBtn").addEventListener("click", async () => {
      try {
        $("clientsLog").textContent = "Скачиваю Bitrix…";
        const data = await api("/sync", { method: "POST", body: "{}" });
        $("clientsLog").textContent = JSON.stringify(data, null, 2);
        await loadClients();
        await loadDash();
      } catch (e) {
        $("clientsLog").textContent = String(e);
      }
    });
    $("clientsRebuildBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/modules/clients/rebuild-outbox", {
          method: "POST",
          body: "{}",
        });
        $("clientsLog").textContent = JSON.stringify(data, null, 2);
        await loadDash();
      } catch (e) {
        $("clientsLog").textContent = String(e);
      }
    });
    $("clientsReloadBtn").addEventListener("click", () => loadClients().catch((e) => ($("clientsLog").textContent = String(e))));
    $("dadataLookupBtn").addEventListener("click", () =>
      dadataLookup(false).catch((e) => ($("dadataLog").textContent = String(e)))
    );
    $("dadataLookupForceBtn").addEventListener("click", () =>
      dadataLookup(true).catch((e) => ($("dadataLog").textContent = String(e)))
    );
    $("dadataEnrichBtn").addEventListener("click", async () => {
      try {
        const n = Number($("dadataEnrichN").value || 50);
        const qs = new URLSearchParams({
          limit: String(n),
          force: "false",
          only_missing_director: "true",
        });
        const data = await api("/api/modules/dadata/enrich?" + qs.toString(), {
          method: "POST",
          body: "{}",
        });
        $("dadataLog").textContent = JSON.stringify(data, null, 2);
        await loadDadataStatus();
      } catch (e) {
        $("dadataLog").textContent = String(e);
      }
    });
    $("dadataPushBitrixBtn").addEventListener("click", async () => {
      try {
        const n = Number($("dadataEnrichN").value || 50);
        const qs = new URLSearchParams({
          limit: String(n),
          only_not_pushed: "true",
        });
        $("dadataLog").textContent = "Пишем в Bitrix…";
        const data = await api("/api/modules/dadata/push-bitrix?" + qs.toString(), {
          method: "POST",
          body: "{}",
        });
        $("dadataLog").textContent = JSON.stringify(data, null, 2);
        await loadDadataStatus();
      } catch (e) {
        $("dadataLog").textContent = String(e);
      }
    });
    $("dadataCacheBtn").addEventListener("click", async () => {
      try {
        const data = await api("/api/modules/dadata/cache?limit=40");
        $("dadataLog").textContent = JSON.stringify(data.counts || {}, null, 2);
        renderDadataRows(data.items || []);
      } catch (e) {
        $("dadataLog").textContent = String(e);
      }
    });
    $("clientsSearchBtn").addEventListener("click", () => loadClientsEmails().catch((e) => ($("clientsLog").textContent = String(e))));
    $("checkRepliesBtn").addEventListener("click", async () => {
      try {
        logAction(await api("/check-replies", { method: "POST", body: "{}" }));
        await loadDash();
      } catch (e) {
        logAction(String(e));
      }
    });
    $("dryRunBtn").addEventListener("click", async () => {
      try {
        logAction(await api("/send-batch", { method: "POST", body: JSON.stringify({ limit: 5, dry_run: true }) }));
      } catch (e) {
        logAction(String(e));
      }
    });
    $("sendBtn").addEventListener("click", async () => {
      const n = Number($("sendN").value || 1);
      if (!confirm(`Отправить ${n} писем из очереди сейчас? Нужен статус «Идёт» (Старт).`)) return;
      try {
        logAction(await api("/send-batch", { method: "POST", body: JSON.stringify({ limit: n, dry_run: false }) }));
        await loadDash();
      } catch (e) {
        logAction(String(e));
      }
    });

    async function doSendOne(dry) {
      const to = ($("oneTo").value || "").trim();
      if (!to) {
        logAction("Укажите email в поле «Кому»");
        return;
      }
      if (!dry && !confirm(`Отправить одно письмо на ${to}?`)) return;
      try {
        logAction(
          await api("/send-one", {
            method: "POST",
            body: JSON.stringify({
              to,
              contact_name: ($("oneName").value || "").trim() || null,
              dry_run: !!dry,
              create_bitrix_deal: false,
            }),
          })
        );
        if (!dry) await loadDash();
      } catch (e) {
        logAction(String(e));
      }
    }
    $("oneDryBtn").addEventListener("click", () => doSendOne(true));
    $("oneSendBtn").addEventListener("click", () => doSendOne(false));

    $("outboxLoad").addEventListener("click", () => loadOutbox().catch(logAction));
    $("repliesLoad").addEventListener("click", () => loadReplies().catch(logAction));
    if ($("inboxLoad")) {
      $("inboxLoad").addEventListener("click", () => loadInbox(true).catch(logAction));
      $("inboxLoadAll").addEventListener("click", () => loadInbox(false).catch(logAction));
      $("seqStatusBtn").addEventListener("click", async () => {
        try {
          const data = await api("/api/modules/sequences/status");
          $("seqLog").textContent = JSON.stringify(data, null, 2);
        } catch (e) {
          logAction(String(e));
        }
      });
      $("inboxBody").addEventListener("click", async (ev) => {
        const btn = ev.target.closest("button[data-inbox-id]");
        if (!btn) return;
        try {
          await api("/api/modules/replies/inbox/" + btn.dataset.inboxId + "/processed", {
            method: "POST",
            body: "{}",
          });
          await loadInbox(true);
        } catch (e) {
          logAction(String(e));
        }
      });
    }
    $("outboxBody").addEventListener("click", async (ev) => {
      const btn = ev.target.closest("button[data-id]");
      if (!btn) return;
      try {
        await api("/api/outbox/" + btn.dataset.id, {
          method: "PATCH",
          body: JSON.stringify({ status: btn.dataset.st }),
        });
        await loadOutbox();
      } catch (e) {
        logAction(String(e));
      }
    });

    $("letterPreview").addEventListener("click", async () => {
      try {
        await applyCampaignContacts({ quiet: true });
        const data = await api("/api/preview", {
          method: "POST",
          body: JSON.stringify(campaignPreviewPayload()),
        });
        $("previewSubject").textContent = data.subject || "";
        $("previewPlain").textContent = data.plain || "";
        // Open <details> first — painting into a closed panel leaves the white preview blank.
        const adv = $("letterAdvanced");
        if (adv) adv.open = true;
        paintPreviewHtml($("previewFrame"), data.html || "");
        refreshSignatureLive();
        if ($("letterLog")) {
          $("letterLog").hidden = false;
          const phone = ($("letterPhone").value || "").trim();
          const phoneOk = !phone || (data.plain || "").includes(phone);
          $("letterLog").textContent =
            (data.attach_presentation
              ? "К письму будет прикреплена презентация PDF. "
              : "Презентация не прикрепляется. ") +
            (phoneOk
              ? phone
                ? `Телефон в письме: ${phone}`
                : "Телефон не указан."
              : "Телефон не попал в текст — проверьте шаблон подписи ({phone_line}) и «Применить контакты».");
        }
      } catch (e) {
        logAction(String(e));
      }
    });

    if ($("letterApplyContacts")) {
      $("letterApplyContacts").addEventListener("click", async () => {
        try {
          await applyCampaignContacts();
        } catch (e) {
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = String(e);
          }
        }
      });
    }
    ["letterCompany", "letterWebsite", "letterEmail", "letterPhone", "letterSignature"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.addEventListener("input", refreshSignatureLive);
      el.addEventListener("change", refreshSignatureLive);
    });

    if ($("letterLogoFile")) {
      $("letterLogoFile").addEventListener("change", async () => {
        const file = $("letterLogoFile").files && $("letterLogoFile").files[0];
        if (!file) return;
        try {
          const fd = new FormData();
          fd.append("file", file);
          const data = await api("/api/brand/logo", { method: "POST", body: fd });
          setLogoPreview(data.logo_url || "");
          if ($("letterLogoEnabled")) $("letterLogoEnabled").checked = true;
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = "Микрологотип загружен.";
          }
        } catch (e) {
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = String(e);
          }
        } finally {
          $("letterLogoFile").value = "";
        }
      });
    }
    if ($("letterLogoReset")) {
      $("letterLogoReset").addEventListener("click", async () => {
        try {
          const data = await api("/api/brand/logo", { method: "DELETE" });
          setLogoPreview(data.logo_url || "");
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = "Логотип сброшен на стандартный Quantum Labs.";
          }
        } catch (e) {
          logAction(String(e));
        }
      });
    }

    if ($("letterApplyPack")) {
      $("letterApplyPack").addEventListener("click", async () => {
        try {
          const packId =
            selectedPackId ||
            document.querySelector('input[name="packId"]:checked')?.value ||
            "lombards";
          const data = await api("/api/packs/apply", {
            method: "POST",
            body: JSON.stringify({
              pack_id: packId,
              attach_presentation: $("letterAttachPdf") ? $("letterAttachPdf").checked : true,
            }),
          });
          settingsCache = data.settings || settingsCache;
          await loadSettingsIntoForms();
          renderPackCards(packId);
          await previewPack(packId, true);
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent =
              `Применена отрасль «${(data.pack && data.pack.title) || packId}». Цепочка follow-up активна.`;
          }
          logAction({ ok: true, pack: packId, updated: data.updated });
        } catch (e) {
          if ($("letterLog")) $("letterLog").hidden = false;
          if ($("letterLog")) $("letterLog").textContent = String(e);
          logAction(String(e));
        }
      });
    }

    $("letterSave").addEventListener("click", async () => {
      try {
        const payload = {
          OUTREACH_SUBJECT: $("letterSubject").value,
          OUTREACH_COMPANY_NAME: $("letterCompany").value,
          OUTREACH_WEBSITE: $("letterWebsite").value,
          OUTREACH_CONTACT_PHONE: $("letterPhone").value,
          OUTREACH_CONTACT_EMAIL: $("letterEmail") ? $("letterEmail").value : "",
          OUTREACH_SIGNATURE: $("letterSignature") ? $("letterSignature").value : "",
          OUTREACH_LOGO_URL: ($("letterLogoPreview") && $("letterLogoPreview").getAttribute("src")) || "",
          OUTREACH_LOGO_ENABLED: $("letterLogoEnabled") && $("letterLogoEnabled").checked ? "true" : "false",
          OUTREACH_TEMPLATE_PLAIN: $("letterPlain").value,
          OUTREACH_TEMPLATE_HTML: $("letterHtml").value,
          OUTREACH_ATTACH_PRESENTATION: $("letterAttachPdf") && $("letterAttachPdf").checked ? "true" : "false",
          OUTREACH_SEQUENCE_PACK: selectedPackId || settingsCache?.OUTREACH_SEQUENCE_PACK || "",
          SEQUENCES_ENABLED: "true",
        };
        const data = await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: payload }) });
        if ($("letterLog")) {
          $("letterLog").hidden = false;
          $("letterLog").textContent = "Кампания сохранена.";
        }
        logAction(data);
      } catch (e) {
        logAction(String(e));
      }
    });

    $("schedSave").addEventListener("click", async () => {
      try {
        const payload = {
          RUN_RESPECT_WINDOW: $("runRespectWindow").checked ? "true" : "false",
          SCHEDULE_WINDOW_START: String($("schedStart").value),
          SCHEDULE_WINDOW_END: String($("schedEnd").value),
          SCHEDULE_TIMEZONE: $("schedTz").value,
          SCHEDULE_BATCH_SIZE: String($("schedBatch").value),
          SCHEDULE_TICK_SECONDS: String($("schedTick").value),
        };
        logAction(await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: payload }) }));
      } catch (e) {
        logAction(String(e));
      }
    });

    $("settingsSave").addEventListener("click", async () => {
      try {
        const payload = {
          OUTREACH_DAILY_LIMIT: String($("setDaily").value),
          OUTREACH_DELAY_MIN_SECONDS: String($("setDelayMin").value),
          OUTREACH_DELAY_MAX_SECONDS: String($("setDelayMax").value),
          BITRIX_CREATE_DEAL: $("setDeal").checked ? "true" : "false",
          BITRIX_ASSIGNED_BY_ID: String($("setAssigned").value),
          BITRIX_DEAL_STAGE_ID: $("setStage").value,
          REPLY_WATCH_ENABLED: $("setReplyWatch").checked ? "true" : "false",
        };
        logAction(await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: payload }) }));
        await loadDash();
      } catch (e) {
        logAction(String(e));
      }
    });

    $("antibanSave").addEventListener("click", async () => {
      try {
        const payload = {
          WARMUP_ENABLED: $("warmupEnabled").checked ? "true" : "false",
          DOMAIN_DAILY_CAP: String($("domainCap").value),
          TRACKING_PLUS_REPLY_TO: $("plusReply").checked ? "true" : "false",
          OPEN_TRACKING_ENABLED: $("openTracking").checked ? "true" : "false",
        };
        $("antibanLog").textContent = JSON.stringify(
          await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: payload }) }),
          null,
          2
        );
        await loadAntiban();
      } catch (e) {
        $("antibanLog").textContent = String(e);
      }
    });
    $("plusPreviewBtn").addEventListener("click", async () => {
      try {
        $("antibanLog").textContent = JSON.stringify(
          await api("/api/modules/tracking/preview-plus?outbox_id=1", {
            method: "POST",
            body: "{}",
          }),
          null,
          2
        );
      } catch (e) {
        $("antibanLog").textContent = String(e);
      }
    });
    $("suppAdd").addEventListener("click", async () => {
      try {
        await api("/api/modules/deliverability/suppression", {
          method: "POST",
          body: JSON.stringify({
            email: $("suppEmail").value,
            reason: $("suppReason").value || "manual",
          }),
        });
        $("suppEmail").value = "";
        await loadSuppression();
      } catch (e) {
        $("antibanLog").textContent = String(e);
      }
    });
    $("suppReload").addEventListener("click", () => loadSuppression().catch((e) => ($("antibanLog").textContent = String(e))));
    $("eventsReload").addEventListener("click", () => loadEvents().catch((e) => ($("antibanLog").textContent = String(e))));
    $("reportReload").addEventListener("click", () => loadReport().catch(logAction));
    $("suppBody").addEventListener("click", async (ev) => {
      const btn = ev.target.closest("button[data-supp]");
      if (!btn) return;
      try {
        await api("/api/modules/deliverability/suppression/" + encodeURIComponent(btn.dataset.supp), {
          method: "DELETE",
        });
        await loadSuppression();
      } catch (e) {
        $("antibanLog").textContent = String(e);
      }
    });

    if (EMBEDDED) {
      try {
        await api("/api/dashboard");
        showApp();
        await loadDash();
        await loadSettingsIntoForms();
        await loadPacks();
        // default tab is campaign
        if ($("pageHint")) $("pageHint").textContent = hints.letter || "";
        return;
      } catch (e) {
        showLogin();
        if ($("loginError")) $("loginError").textContent = String(e.message || e);
        return;
      }
    }

    if (token) {
      try {
        await api("/api/dashboard");
        showApp();
        await loadDash();
        await loadSettingsIntoForms();
        await loadPacks();
        // default tab is campaign
        if ($("pageHint")) $("pageHint").textContent = hints.letter || "";
        return;
      } catch (_) {
        showLogin();
      }
    }
    showLogin();
  }

  boot();
})();
