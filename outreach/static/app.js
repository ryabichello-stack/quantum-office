(() => {
  const titles = {
    letter: "Кампания",
    outbox: "Очередь",
    inbox: "Входящие",
    report: "Результат",
    clients: "Клиенты",
    lpr: "ЛПР",
    studio: "Студия",
    settings: "Настройки",
  };
  const hints = {
    letter: "Отрасль, цепочка, тест — затем Старт и Очередь",
    outbox: "Пачки, окна по TZ, фильтры и действия по строке",
    inbox: "Классификация ответов и привязка к письмам",
    report: "Воронка, динамика, последние письма",
    clients: "Bitrix → geo → очередь; список с городом и TZ",
    lpr: "Комитет ЛПР: поиск, покрытие ролей, approve / task",
    studio: "Контент, Radar и видео — с ручным утверждением",
    settings: "Локальные окна, лимиты, anti-ban",
  };

  let outboxItemsCache = [];
  let outboxTotalCache = 0;
  let lastBatchMeta = { deferred_window_count: null, at: null };

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
  let tgTokenConfigured = false;

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

  async function downloadApi(path, filename) {
    const res = await fetch(BASE + path, {
      credentials: "same-origin",
      headers: !EMBEDDED && token ? { "X-Outreach-Token": token } : {},
    });
    if (!res.ok) {
      throw new Error(`export failed: ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename || "export.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
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
    if (BASE) return BASE.replace(/\/$/, "") + "/assets/brand/icons/v2/" + name + ".png";
    return "https://a.47z.ru/_ava_outreach/assets/brand/icons/v2/" + name + ".png";
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
    const el = $("actionLog") || $("queueLog");
    if (!el) return;
    el.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
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
  /** @type {Array<{step:number,delay_days:number,label:string,subject:string,plain:string,html:string,attach_presentation:boolean}>} */
  let letterChain = [];
  let activeLetterIdx = 0;
  let letterDirty = false;

  function blankLetter(partial = {}) {
    const n = (letterChain.length || 0) + 1;
    const prevDelay =
      letterChain.length > 0 ? Number(letterChain[letterChain.length - 1].delay_days) || 0 : -3;
    return {
      step: n,
      delay_days: partial.delay_days != null ? Number(partial.delay_days) : prevDelay + 3,
      label: partial.label || `letter_${n}`,
      subject: partial.subject || "",
      plain: partial.plain || "{greeting}\n\n\n{signature}",
      html: partial.html || "",
      attach_presentation: !!partial.attach_presentation,
    };
  }

  function readLetterFormIntoChain() {
    if (!letterChain.length) return;
    const i = Math.max(0, Math.min(activeLetterIdx, letterChain.length - 1));
    const cur = letterChain[i];
    cur.subject = ($("letterSubject") && $("letterSubject").value) || "";
    cur.plain = ($("letterPlain") && $("letterPlain").value) || "";
    cur.html = ($("letterHtml") && $("letterHtml").value) || "";
    cur.delay_days = Math.max(0, Number(($("letterDelayDays") && $("letterDelayDays").value) || 0));
    cur.label = (($("letterLabel") && $("letterLabel").value) || "").trim() || `letter_${i + 1}`;
    cur.attach_presentation = !!($("letterAttachPdf") && $("letterAttachPdf").checked);
    cur.step = i + 1;
  }

  function writeLetterFormFromChain() {
    if (!letterChain.length) {
      letterChain = [blankLetter({ delay_days: 0, label: "intro", attach_presentation: true })];
      activeLetterIdx = 0;
    }
    activeLetterIdx = Math.max(0, Math.min(activeLetterIdx, letterChain.length - 1));
    const cur = letterChain[activeLetterIdx];
    if ($("letterSubject")) $("letterSubject").value = cur.subject || "";
    if ($("letterPlain")) $("letterPlain").value = cur.plain || "";
    if ($("letterHtml")) $("letterHtml").value = cur.html || "";
    if ($("letterDelayDays")) $("letterDelayDays").value = String(cur.delay_days ?? 0);
    if ($("letterLabel")) $("letterLabel").value = cur.label || "";
    if ($("letterAttachPdf")) $("letterAttachPdf").checked = !!cur.attach_presentation;
    ["letterPlain", "letterHtml", "letterSignature"].forEach((id) => {
      if ($(id)) autoGrowField($(id));
    });
    renderLetterTabs();
  }

  function renderLetterTabs() {
    const box = $("letterTabs");
    if (!box) return;
    box.innerHTML = letterChain
      .map((s, idx) => {
        const day = s.delay_days != null ? s.delay_days : 0;
        const label = escapeHtml(s.label || `letter_${idx + 1}`);
        const active = idx === activeLetterIdx ? " active" : "";
        const pdf = s.attach_presentation ? " · PDF" : "";
        return `<button type="button" class="letter-tab${active}" data-letter-idx="${idx}" role="tab" aria-selected="${
          idx === activeLetterIdx ? "true" : "false"
        }">Письмо ${idx + 1}<small>день ${day}${pdf}</small><span class="letter-tab-sub">${label}</span></button>`;
      })
      .join("");
    box.querySelectorAll("[data-letter-idx]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const next = Number(btn.getAttribute("data-letter-idx"));
        if (Number.isNaN(next) || next === activeLetterIdx) return;
        readLetterFormIntoChain();
        activeLetterIdx = next;
        writeLetterFormFromChain();
      });
    });
    if ($("packDraftBadge")) {
      const pack = packsCache.find((p) => p.id === selectedPackId);
      const show = !!(pack && pack.has_draft) || letterDirty;
      $("packDraftBadge").hidden = !show;
      $("packDraftBadge").textContent = letterDirty
        ? "Есть несохранённые правки цепочки"
        : "Есть сохранённый черновик цепочки";
    }
    if ($("letterDelBtn")) $("letterDelBtn").disabled = letterChain.length <= 1;
    if ($("letterMoveUp")) $("letterMoveUp").disabled = activeLetterIdx <= 0;
    if ($("letterMoveDown"))
      $("letterMoveDown").disabled = activeLetterIdx >= letterChain.length - 1;
  }

  function setLetterChainFromPack(pack, { fill = true, keepIndex = false } = {}) {
    const steps = (pack && pack.steps) || [];
    letterChain = steps.map((s, i) => ({
      step: Number(s.step) || i + 1,
      delay_days: Number(s.delay_days) || 0,
      label: s.label || `letter_${i + 1}`,
      subject: s.subject || "",
      plain: s.plain || "",
      html: s.html || "",
      attach_presentation: !!s.attach_presentation,
    }));
    if (!letterChain.length) {
      letterChain = [
        blankLetter({
          delay_days: 0,
          label: "intro",
          subject: (pack && pack.subject) || "",
          plain: (pack && pack.plain) || "",
          html: (pack && pack.html) || "",
          attach_presentation: !!(pack && pack.attach_presentation_default),
        }),
      ];
    }
    if (!keepIndex) activeLetterIdx = 0;
    else activeLetterIdx = Math.max(0, Math.min(activeLetterIdx, letterChain.length - 1));
    letterDirty = false;
    if (fill) writeLetterFormFromChain();
    else renderLetterTabs();
  }

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
        const draft = p.has_draft ? " · черновик" : "";
        return `<label class="pack-card ${on}">
          <input type="radio" name="packId" value="${escapeHtml(p.id)}" ${p.id === activeId ? "checked" : ""} />
          <span>
            <strong>${escapeHtml(p.title)}</strong>
            <small>${escapeHtml(p.short || "")}${draft}</small>
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
      if (active) {
        if (letterChain.length && letterDirty && selectedPackId === active) {
          renderLetterTabs();
        } else {
          await previewPack(active, true);
        }
      }
    } catch (err) {
      if ($("packCards")) $("packCards").textContent = String(err.message || err);
    }
  }

  function formatBytes(n) {
    const x = Number(n) || 0;
    if (x < 1024) return x + " B";
    if (x < 1024 * 1024) return (x / 1024).toFixed(1) + " KB";
    return (x / (1024 * 1024)).toFixed(1) + " MB";
  }

  function formatPresentationMeta(meta, packTitle) {
    if (!meta || !meta.exists) {
      return packTitle
        ? `Презентация для «${packTitle}»: файл ещё не загружен`
        : "Презентация отрасли: файл ещё не загружен";
    }
    const srcLabel =
      meta.source === "custom"
        ? "загружена вами"
        : meta.source === "pack"
          ? "базовая отраслевая"
          : meta.source === "default"
            ? "общая Quantum Payouts"
            : meta.source || "";
    const when = meta.mtime ? new Date(meta.mtime * 1000).toLocaleString("ru-RU") : "";
    return (
      `PDF: ${meta.filename || "presentation.pdf"} · ${formatBytes(meta.bytes)}` +
      (srcLabel ? ` · ${srcLabel}` : "") +
      (when ? ` · ${when}` : "")
    );
  }

  async function refreshPresentationMeta(packId) {
    const pid = packId || selectedPackId;
    if (!pid || !$("letterPdfMeta")) return null;
    try {
      const data = await api("/api/packs/" + encodeURIComponent(pid) + "/presentation");
      const meta = data.presentation || {};
      const pack = packsCache.find((p) => p.id === pid);
      $("letterPdfMeta").textContent = formatPresentationMeta(meta, pack && pack.title);
      if ($("letterPdfReset")) $("letterPdfReset").disabled = !meta.can_reset;
      return meta;
    } catch (e) {
      $("letterPdfMeta").textContent = String(e.message || e);
      return null;
    }
  }

  async function previewPack(packId, fillEditors = true) {
    if (!packId) return;
    const data = await api("/api/packs/" + encodeURIComponent(packId));
    const pack = data.pack || {};
    selectedPackId = pack.pack_id || packId;
    const idx = packsCache.findIndex((p) => p.id === selectedPackId);
    if (idx >= 0) packsCache[idx].has_draft = !!pack.has_draft;
    if ($("packActiveMeta")) {
      $("packActiveMeta").textContent =
        `Выбрано: ${pack.title || packId} — ${pack.short || ""} · ${(pack.steps || []).length} писем`;
    }
    if ($("campaignStrip")) {
      const steps = (pack.steps || []).length;
      $("campaignStrip").textContent =
        `Активная отрасль: ${pack.title || packId} · ${steps} писем в цепочке · после правок — «Применить отрасль» и тест`;
    }
    if ($("campaignChainSummary")) {
      const steps = (pack.steps || []).length;
      $("campaignChainSummary").textContent = `Цепочка писем (${steps} шагов)`;
    }
    if ($("letterPdfMeta")) {
      $("letterPdfMeta").textContent = formatPresentationMeta(
        pack.presentation_meta,
        pack.title || packId
      );
      if ($("letterPdfReset")) {
        $("letterPdfReset").disabled = !(pack.presentation_meta && pack.presentation_meta.can_reset);
      }
    }
    setLetterChainFromPack(pack, { fill: fillEditors, keepIndex: !fillEditors });
    await refreshPresentationMeta(selectedPackId);
    return pack;
  }

  async function saveLetterChain() {
    readLetterFormIntoChain();
    const packId =
      selectedPackId ||
      document.querySelector('input[name="packId"]:checked')?.value ||
      "";
    if (!packId) throw new Error("Сначала выберите отрасль");
    const data = await api("/api/packs/" + encodeURIComponent(packId) + "/letters", {
      method: "PUT",
      body: JSON.stringify({ steps: letterChain }),
    });
    if (data.settings) settingsCache = data.settings;
    if (data.pack) {
      const idx = packsCache.findIndex((p) => p.id === packId);
      if (idx >= 0) packsCache[idx].has_draft = !!data.pack.has_draft;
      setLetterChainFromPack(data.pack, { fill: true, keepIndex: true });
    }
    letterDirty = false;
    renderLetterTabs();
    return data;
  }

  function setEnabledBadge(on) {
    // legacy no-op kept for older calls — mirror into run badge if needed
    if (typeof on === "boolean") {
      /* ignore */
    }
  }

  function renderDailyChart(daily, targetId) {
    const box = $(targetId || "dailyChart");
    if (!box) return;
    const max = Math.max(1, ...(daily || []).map((d) => d.sent || 0));
    box.innerHTML = (daily || []).length
      ? daily
          .map((d) => {
            const pct = Math.round(((d.sent || 0) / max) * 100);
            return `<div class="bar-row"><span>${d.day}</span><div class="bar"><span style="width:${pct}%"></span></div><span>${d.sent}</span></div>`;
          })
          .join("")
      : `<p class="muted tight">Пока нет отправок</p>`;
  }

  function renderHeaderKpi(dash, health) {
    const box = $("headerKpi");
    if (!box) return;
    const c = (dash.outbox && dash.outbox.counts) || {};
    const e = dash.engagement || {};
    const geo = (dash.clients && dash.clients.geo) || {};
    const st = (dash.run_state || (dash.runner && dash.runner.state) || "stopped").toLowerCase();
    const stLabel = { playing: "Идёт", paused: "Пауза", stopped: "Стоп" }[st] || st;
    const stCls = st in { playing: 1, paused: 1, stopped: 1 } ? st : "stopped";
    const withTz = geo.with_timezone != null ? geo.with_timezone : "—";
    const companies = geo.companies != null ? geo.companies : "—";
    const tg = (health && health.telegram) || {};
    const oncall = (health && health.oncall) || {};
    const tgLabel = tg.ready ? "TG ✓" : tg.token_configured ? "TG …" : "TG —";
    const oncallLabel = oncall.ready ? "On-call ✓" : oncall.webhook_configured ? "On-call …" : "On-call —";
    const items = [
      ["Очередь", c.pending || 0],
      ["Сегодня", dash.outbox ? dash.outbox.sent_today : 0],
      ["Отправлено", e.sent || c.sent || 0],
      ["Открыто", e.opened || 0],
      ["Ответы", e.replied || c.replied || 0],
      ["Geo TZ", `${withTz}/${companies}`],
    ];
    box.innerHTML =
      items
        .map(
          ([l, n]) =>
            `<div class="kpi-item"><span class="kpi-n">${n}</span><span class="kpi-l">${l}</span></div>`
        )
        .join("") +
      `<div class="kpi-item kpi-state ${stCls}"><span class="kpi-n">${stLabel}</span><span class="kpi-l">Статус</span></div>` +
      `<div class="kpi-item kpi-pill ${tg.ready ? "ok" : "warn"}"><span class="kpi-n">${tgLabel}</span><span class="kpi-l">Panel</span></div>` +
      `<div class="kpi-item kpi-pill ${oncall.ready ? "ok" : "warn"}"><span class="kpi-n">${oncallLabel}</span><span class="kpi-l">Ops</span></div>`;
  }

  function renderStats(dash, health) {
    renderHeaderKpi(dash, health);
    renderDailyChart(dash.daily || [], "dailyChart");
  }

  async function loadDash() {
    const [dash, health] = await Promise.all([
      api("/api/dashboard"),
      api("/api/ops/health").catch(() => ({})),
    ]);
    renderStats(dash, health);
    setRunStateBadge(dash.run_state || (dash.runner && dash.runner.state) || "stopped");
    await loadOpsSummary().catch(() => {});
  }

  function goToTab(tab) {
    const btn = document.querySelector(`.tabs button[data-tab="${tab}"]`);
    if (btn) btn.click();
  }

  function renderOpsAlerts(alerts) {
    const box = $("opsAlerts");
    if (!box) return;
    const items = alerts || [];
    if (!items.length) {
      box.classList.add("hidden");
      box.innerHTML = "";
      return;
    }
    box.classList.remove("hidden");
    box.innerHTML = items
      .map(
        (a) => `<div class="ops-alert ${escapeHtml(a.level || "info")}">
          <div><strong>${escapeHtml(a.title || "")}</strong><br><span class="muted">${escapeHtml(a.detail || "")}</span></div>
          ${a.tab ? `<button type="button" class="small btn-quiet" data-ops-tab="${escapeHtml(a.tab)}">Открыть</button>` : ""}
        </div>`
      )
      .join("");
    box.querySelectorAll("[data-ops-tab]").forEach((btn) => {
      btn.addEventListener("click", () => goToTab(btn.dataset.opsTab));
    });
  }

  function renderOpsActions(data) {
    const section = $("opsActions");
    const list = $("opsActionsList");
    const meta = $("opsActionsMeta");
    if (!section || !list) return;
    const actions = (data && data.actions) || [];
    const counts = (data && data.counts) || {};
    if (!actions.length) {
      section.classList.add("hidden");
      list.innerHTML = "";
      if (meta) meta.textContent = "";
      return;
    }
    section.classList.remove("hidden");
    if (meta) {
      meta.textContent = `Всего ${actions.length} · входящие ${counts.inbox_unprocessed || 0}`;
    }
    list.innerHTML = actions
      .map(
        (a) => `<button type="button" class="ops-action sev-${escapeHtml(a.severity || "medium")}" data-ops-action="${escapeHtml(a.id || "")}" data-ops-tab="${escapeHtml(a.tab || "")}">
          <span class="ops-action-main">
            <div class="ops-action-title">${escapeHtml(a.title || "")}</div>
            <div class="ops-action-detail">${escapeHtml(a.detail || "")}</div>
          </span>
          <span class="muted">→</span>
        </button>`
      )
      .join("");
    list.querySelectorAll("[data-ops-action]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.opsTab;
        if (tab) goToTab(tab);
      });
    });
  }

  async function loadOpsSummary() {
    const data = await api("/api/ops/summary");
    renderOpsAlerts(data.alerts || []);
    renderOpsActions(data);
    return data;
  }

  let opsPollTimer = null;
  function startOpsPolling() {
    if (opsPollTimer) clearInterval(opsPollTimer);
    opsPollTimer = setInterval(() => {
      if (document.hidden) return;
      loadOpsSummary().catch(() => {});
    }, 60000);
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
    const [data, dash] = await Promise.all([
      api(`/api/modules/analytics/report?days=${days}&recent_limit=50`),
      api("/api/dashboard"),
    ]);
    renderDailyChart(dash.daily || [], "dailyChart");
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

    const seq = data.sequence_steps || {};
    const steps = seq.steps || [];
    const seqMax = Math.max(1, ...(steps.map((s) => s.reached || 0)));
    if ($("reportSequenceSteps")) {
      $("reportSequenceSteps").innerHTML = steps.length
        ? steps
            .map(
              (s) => `<div class="seq-step-row">
              <span>Шаг ${s.step}</span>
              <div class="seq-step-bar"><i style="width:${Math.round(((s.reached || 0) / seqMax) * 100)}%"></i></div>
              <b>${s.reached || 0}</b>
              <span class="muted">${s.pct_of_total != null ? s.pct_of_total + "% всего" : ""}${
                s.pct_from_prev != null ? ` · ${s.pct_from_prev}% от шаг ${(s.step || 1) - 1 || 1}` : ""
              }</span>
            </div>`
            )
            .join("") +
            `<p class="muted tight" style="margin-top:0.35rem">Всего цепочек: ${seq.total_sequences || 0}</p>`
        : `<p class="muted tight">Нет данных по цепочкам</p>`;
    }

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

  function pill(cls, label) {
    return `<span class="integration-pill ${cls}"><span class="dot"></span>${escapeHtml(label)}</span>`;
  }

  function companyLink(companyId, label) {
    const cid = String(companyId || "").trim();
    if (!cid) return `<span class="muted">—</span>`;
    const text = escapeHtml(label || cid);
    return `<button type="button" class="linkish company-open" data-company-id="${escapeHtml(cid)}">${text}</button>`;
  }

  function closeCompanyCard() {
    const peel = $("companyPeelAway");
    if (!peel) return;
    peel.classList.remove("is-open");
    window.setTimeout(() => {
      if (!peel.classList.contains("is-open")) peel.hidden = true;
    }, 260);
    document.body.classList.remove("peel-away-open");
  }

  let activeInboxThreadId = null;
  let activeInboxDraft = "";

  function closeInboxThread() {
    const peel = $("inboxThreadPeelAway");
    if (!peel) return;
    peel.classList.remove("is-open");
    window.setTimeout(() => {
      if (!peel.classList.contains("is-open")) peel.hidden = true;
    }, 260);
    document.body.classList.remove("peel-away-open");
    activeInboxThreadId = null;
    activeInboxDraft = "";
    if ($("inboxReplyBody")) $("inboxReplyBody").value = "";
    if ($("inboxReplyStatus")) $("inboxReplyStatus").textContent = "";
    const enrich = $("inboxThreadEnrichment");
    if (enrich) {
      enrich.hidden = true;
      enrich.innerHTML = "";
    }
    const draftBtn = $("inboxReplyUseDraft");
    if (draftBtn) draftBtn.hidden = true;
  }

  function renderInboxThreadMessages(messages) {
    return (messages || [])
      .map((m) => {
        const dir = m.direction === "outbound" ? "outbound" : "inbound";
        const who =
          dir === "outbound"
            ? `Мы → ${escapeHtml(m.to || "")}`
            : escapeHtml(m.from || m.to || "");
        const kind =
          m.kind === "operator"
            ? "оператор"
            : m.kind === "outreach"
              ? "outreach"
              : m.classification
                ? escapeHtml(m.classification)
                : "ответ";
        return `<article class="thread-msg ${dir}">
          <div class="thread-msg-head"><span>${who} · ${kind}</span><span>${escapeHtml(m.at || "")}</span></div>
          <div class="thread-msg-subject muted">${escapeHtml(m.subject || "")}</div>
          <div class="thread-msg-body">${escapeHtml(m.body || "")}</div>
        </article>`;
      })
      .join("");
  }

  function renderInboxEnrichment(enrichment) {
    const el = $("inboxThreadEnrichment");
    const draftBtn = $("inboxReplyUseDraft");
    activeInboxDraft = "";
    if (!el) return;
    if (!enrichment || !enrichment.ok) {
      el.hidden = true;
      el.innerHTML = "";
      if (draftBtn) draftBtn.hidden = true;
      return;
    }
    const acc = enrichment.account || null;
    const person = enrichment.person || null;
    const lead = enrichment.lead || null;
    const next = enrichment.next_action || {};
    const draft = enrichment.suggested_reply || {};
    const bits = [];
    if (acc) {
      bits.push(
        `<div><span class="muted">Account</span> ${escapeHtml(
          acc.legal_name || acc.brand_name || acc.id
        )} · <code>${escapeHtml(acc.lifecycle_status || "")}</code>` +
          (acc.bitrix_company_id
            ? ` · bx ${escapeHtml(String(acc.bitrix_company_id))}`
            : "") +
          `</div>`
      );
    } else {
      bits.push(`<div class="muted">Account ещё не связан — появится после resolve inbound</div>`);
    }
    if (person) {
      bits.push(
        `<div><span class="muted">Person</span> ${escapeHtml(
          person.full_name || person.id
        )}</div>`
      );
    }
    if (lead) {
      bits.push(
        `<div><span class="muted">Lead</span> ${escapeHtml(
          lead.status || ""
        )} · ${escapeHtml(lead.source || "")}</div>`
      );
    }
    if (next.label) {
      bits.push(
        `<div class="inbox-next-action"><span class="muted">Next</span> <strong>${escapeHtml(
          next.label
        )}</strong> <span class="badge">${escapeHtml(next.priority || "")}</span></div>`
      );
    }
    if (draft.approval_required && draft.body) {
      bits.push(
        `<div class="muted tight">Черновик ответа · APPROVAL_REQUIRED (не отправляется автоматически)</div>`
      );
      const cites = draft.citations || [];
      if (cites.length) {
        bits.push(
          `<div class="muted tight">Цитаты: ${cites
            .slice(0, 3)
            .map((c) => escapeHtml((c.source || "") + " · " + (c.ref || "")))
            .join("; ")}</div>`
        );
      }
      activeInboxDraft = draft.body;
      if (draftBtn) draftBtn.hidden = false;
    } else if (draftBtn) {
      draftBtn.hidden = true;
    }
    el.innerHTML = bits.join("");
    el.hidden = false;
  }

  async function openInboxThread(inboxId) {
    const peel = $("inboxThreadPeelAway");
    const title = $("inboxThreadTitle");
    const meta = $("inboxThreadMeta");
    const body = $("inboxThreadBody");
    if (!peel || !inboxId) return;
    activeInboxThreadId = inboxId;
    peel.hidden = false;
    requestAnimationFrame(() => peel.classList.add("is-open"));
    document.body.classList.add("peel-away-open");
    if (title) title.textContent = "Переписка";
    if (meta) meta.textContent = "Загрузка…";
    if (body) body.innerHTML = "<p class='muted tight'>Загрузка…</p>";
    const enrichEl = $("inboxThreadEnrichment");
    if (enrichEl) {
      enrichEl.hidden = true;
      enrichEl.innerHTML = "";
    }
    try {
      const data = await api(`/api/modules/replies/inbox/${encodeURIComponent(inboxId)}/thread`);
      if (title) title.textContent = data.subject || "Переписка";
      if (meta) {
        meta.textContent = [
          data.peer_email || "",
          data.classification ? `класс: ${data.classification}` : "",
          data.company_id ? `company ${data.company_id}` : "",
        ]
          .filter(Boolean)
          .join(" · ");
      }
      renderInboxEnrichment(data.enrichment);
      if (body) {
        body.innerHTML = `<div class="inbox-thread-messages">${renderInboxThreadMessages(
          data.messages
        )}</div>`;
      }
    } catch (e) {
      if (body) body.textContent = String(e);
    }
  }

  async function sendInboxThreadReply() {
    if (!activeInboxThreadId) return;
    const text = ($("inboxReplyBody") && $("inboxReplyBody").value || "").trim();
    const markDone = !($("inboxReplyMarkDone") && !$("inboxReplyMarkDone").checked);
    const status = $("inboxReplyStatus");
    if (!text) {
      if (status) status.textContent = "Введите текст ответа";
      return;
    }
    if (status) status.textContent = "Отправка…";
    try {
      await api(`/api/modules/replies/inbox/${encodeURIComponent(activeInboxThreadId)}/reply`, {
        method: "POST",
        body: JSON.stringify({ body: text, mark_done: markDone }),
      });
      if ($("inboxReplyBody")) $("inboxReplyBody").value = "";
      if (status) status.textContent = "Отправлено";
      await openInboxThread(activeInboxThreadId);
      await loadInbox(true);
    } catch (e) {
      if (status) status.textContent = String(e);
    }
  }

  async function openCompanyCard(companyId) {
    const peel = $("companyPeelAway");
    const body = $("companyCardBody");
    const title = $("companyCardTitle");
    const meta = $("companyCardMeta");
    const cid = String(companyId || "").trim();
    if (!peel || !cid) return;
    peel.hidden = false;
    requestAnimationFrame(() => peel.classList.add("is-open"));
    document.body.classList.add("peel-away-open");
    if (title) title.textContent = `Компания ${cid}`;
    if (meta) meta.textContent = "Загрузка…";
    if (body) body.textContent = "Загрузка…";
    try {
      const data = await api(`/api/modules/clients/company/${encodeURIComponent(cid)}`);
      const c = data.company || {};
      if (title) title.textContent = c.title || `Компания ${cid}`;
      if (meta) {
        meta.textContent = [
          c.inn ? `ИНН ${c.inn}` : "",
          c.city || "",
          c.timezone || "",
          c.director_greeting || c.director_name || "",
        ]
          .filter(Boolean)
          .join(" · ");
      }
      const outboxRows = (data.outbox || [])
        .map(
          (r) =>
            `<tr><td>${escapeHtml(r.email || "")}</td><td>${escapeHtml(r.status || "")}</td><td>${escapeHtml(
              r.sent_at || ""
            )}</td></tr>`
        )
        .join("");
      const seqRows = (data.sequences || [])
        .map(
          (r) =>
            `<tr><td>${escapeHtml(r.email || "")}</td><td>${escapeHtml(String(r.current_step || ""))}</td><td>${escapeHtml(
              r.status || ""
            )}</td></tr>`
        )
        .join("");
      const consentRows = (data.consent || [])
        .map(
          (r) =>
            `<tr><td>${escapeHtml(r.email || "")}</td><td>${escapeHtml(r.status || "")}</td><td>${escapeHtml(
              r.reason || ""
            )}</td></tr>`
        )
        .join("");
      if (body) {
        const dq = data.data_quality || {};
        const dqChecks = (dq.checks || [])
          .map((c) => `<li class="${c.ok ? "ok" : "warn"}">${escapeHtml(c.label)}</li>`)
          .join("");
        body.innerHTML = `
          <section class="peel-quality">
            <h3>Data quality · ${escapeHtml(String(dq.score ?? "—"))}%</h3>
            <ul class="dq-list">${dqChecks || "<li class='muted'>—</li>"}</ul>
          </section>
          <div class="company-card-grid">
            <section><h3>Контакты</h3>${(data.contacts || []).length ? `<ul>${(data.contacts || [])
              .map((r) => `<li>${escapeHtml(r.display_name || "")} · ${escapeHtml(r.primary_email || "")}</li>`)
              .join("")}</ul>` : `<p class="muted tight">Нет контактов</p>`}</section>
            <section><h3>Очередь / отправки</h3>${outboxRows ? `<table><thead><tr><th>Email</th><th>Статус</th><th>Отправлено</th></tr></thead><tbody>${outboxRows}</tbody></table>` : `<p class="muted tight">Нет записей</p>`}</section>
            <section><h3>Цепочки</h3>${seqRows ? `<table><thead><tr><th>Email</th><th>Шаг</th><th>Статус</th></tr></thead><tbody>${seqRows}</tbody></table>` : `<p class="muted tight">Нет цепочек</p>`}</section>
            <section><h3>Consent</h3>${consentRows ? `<table><thead><tr><th>Email</th><th>Статус</th><th>Причина</th></tr></thead><tbody>${consentRows}</tbody></table>` : `<p class="muted tight">Нет записей</p>`}</section>
          </div>`;
      }
    } catch (e) {
      if (body) body.textContent = String(e);
    }
  }

  function renderIntegrationsStatus(health) {
    const box = $("integrationsStatus");
    if (!box || !health) return;
    const tg = health.telegram || {};
    const oncall = health.oncall || {};
    const pills = [
      pill(health.smtp_configured ? "ok" : "bad", "SMTP"),
      pill(health.imap_configured ? "ok" : "warn", "IMAP"),
      pill(health.bitrix_webhook_configured ? "ok" : "warn", "Bitrix"),
      pill(tg.ready ? "ok" : tg.token_configured ? "warn" : "bad", "Telegram"),
      pill(
        oncall.ready ? "ok" : oncall.webhook_configured ? "warn" : "bad",
        "On-call"
      ),
    ];
    box.innerHTML = pills.join("");
  }

  function renderTelegramStatus(health) {
    const box = $("opsTelegramStatus");
    if (!box) return;
    const tg = (health && health.telegram) || {};
    if (tg.ready) {
      box.className = "telegram-status ok tight";
      box.textContent = "Quantum Panel: Telegram подключён (token + chat id).";
    } else if (tg.enabled && tg.token_configured && !tg.chat_id_configured) {
      box.className = "telegram-status warn tight";
      box.textContent = "Token сохранён. Напишите боту /start и нажмите «Найти chat id».";
    } else if (tg.token_configured && !tg.enabled) {
      box.className = "telegram-status warn tight";
      box.textContent = "Token сохранён. Включите Telegram push и укажите chat id.";
    } else {
      box.className = "telegram-status muted tight";
      box.textContent = "Telegram не настроен.";
    }
  }

  async function loadIntegrationsHealth() {
    const health = await api("/api/ops/health");
    renderIntegrationsStatus(health);
    renderTelegramStatus(health);
    return health;
  }

  function currentTelegramToken() {
    const raw = ($("opsNotifyTgToken") && $("opsNotifyTgToken").value || "").trim();
    if (raw && raw !== "••••••••") return raw;
    return null;
  }

  function opsNotifyPayload() {
    const payload = {
      OPS_NOTIFY_ENABLED: $("opsNotifyEnabled").checked ? "true" : "false",
      REPLY_NOTIFY_ENABLED:
        $("replyNotifyEnabled") && $("replyNotifyEnabled").checked ? "true" : "false",
      OPS_NOTIFY_EMAIL_ENABLED: $("opsNotifyEmailEnabled").checked ? "true" : "false",
      OPS_NOTIFY_EMAIL: ($("opsNotifyEmail").value || "").trim(),
      OPS_NOTIFY_TELEGRAM_ENABLED: $("opsNotifyTelegramEnabled").checked ? "true" : "false",
      OPS_NOTIFY_TELEGRAM_CHAT_ID: ($("opsNotifyTgChat").value || "").trim(),
      OPS_NOTIFY_ON_POSITIVE_REPLY: $("opsNotifyOnReply").checked ? "true" : "false",
      OPS_NOTIFY_ON_MAILBOX_PAUSE: $("opsNotifyOnPause").checked ? "true" : "false",
      OPS_NOTIFY_ON_CALLBACK: $("opsNotifyOnCallback").checked ? "true" : "false",
      OPS_NOTIFY_ONCALL_ENABLED: $("opsNotifyOncallEnabled").checked ? "true" : "false",
      OPS_NOTIFY_ONCALL_WEBHOOK_URL: ($("opsNotifyOncallUrl").value || "").trim(),
    };
    const tokenVal = currentTelegramToken();
    if (tokenVal) payload.OPS_NOTIFY_TELEGRAM_BOT_TOKEN = tokenVal;
    const email = ($("opsNotifyEmail").value || "").trim();
    if (email) payload.REPLY_NOTIFY_EMAIL = email;
    return payload;
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
    // Letter subject/plain/html owned by letter-chain editor (loaded via /api/packs).
    if ($("letterSignature")) autoGrowField($("letterSignature"));

    $("schedEnabled").checked = String(s.SCHEDULE_ENABLED).toLowerCase() === "true" || s.SCHEDULE_ENABLED === "1";
    $("runRespectWindow").checked = String(s.RUN_RESPECT_WINDOW || "true").toLowerCase() !== "false";
    $("schedStart").value = s.SCHEDULE_WINDOW_START || 10;
    $("schedEnd").value = s.SCHEDULE_WINDOW_END || 18;
    $("schedTz").value = s.SCHEDULE_TIMEZONE || "Europe/Moscow";
    $("schedBatch").value = s.SCHEDULE_BATCH_SIZE || 1;
    $("schedTick").value = s.SCHEDULE_TICK_SECONDS || 300;

    if ($("localWindowsEnabled")) {
      $("localWindowsEnabled").checked =
        String(s.SCHEDULE_LOCAL_WINDOWS || "true").toLowerCase() !== "false";
    }
    if ($("followupsFirst")) {
      $("followupsFirst").checked =
        String(s.SCHEDULE_FOLLOWUPS_FIRST || "true").toLowerCase() !== "false";
    }
    if ($("preferTueThu")) {
      $("preferTueThu").checked =
        String(s.SCHEDULE_PREFER_TUE_THU || "true").toLowerCase() !== "false";
    }
    if ($("skipRuHolidays")) {
      $("skipRuHolidays").checked =
        String(s.SCHEDULE_SKIP_RU_HOLIDAYS || "true").toLowerCase() !== "false";
    }
    if ($("localSlots")) {
      $("localSlots").value = s.SCHEDULE_SLOTS || "10:00-11:30,14:30-16:30";
    }
    if ($("localAllowedDays")) {
      $("localAllowedDays").value = s.SCHEDULE_ALLOWED_WEEKDAYS || "0,1,2,3,4";
    }
    if ($("localPreferredDays")) {
      $("localPreferredDays").value = s.SCHEDULE_PREFERRED_WEEKDAYS || "1,2,3";
    }
    if ($("localDefaultTz")) {
      $("localDefaultTz").value = s.SCHEDULE_DEFAULT_TIMEZONE || "Europe/Moscow";
    }
    if ($("tzFairness")) {
      const fair = (s.SCHEDULE_TZ_FAIRNESS || "rotate_daily").trim() || "rotate_daily";
      $("tzFairness").value = ["east_first", "west_first", "rotate_daily"].includes(fair)
        ? fair
        : "rotate_daily";
    }
    if ($("oooPauseDays")) {
      $("oooPauseDays").value = s.OOO_PAUSE_DAYS || "7";
    }
    if ($("replyNotifyEnabled")) {
      $("replyNotifyEnabled").checked =
        String(s.REPLY_NOTIFY_ENABLED || "true").toLowerCase() !== "false";
    }
    if ($("opsNotifyEnabled")) {
      $("opsNotifyEnabled").checked = String(s.OPS_NOTIFY_ENABLED || "true").toLowerCase() !== "false";
    }
    if ($("opsNotifyEmailEnabled")) {
      $("opsNotifyEmailEnabled").checked =
        String(s.OPS_NOTIFY_EMAIL_ENABLED || "true").toLowerCase() !== "false";
    }
    if ($("opsNotifyEmail")) {
      $("opsNotifyEmail").value = s.OPS_NOTIFY_EMAIL || s.REPLY_NOTIFY_EMAIL || "";
    }
    if ($("opsNotifyTelegramEnabled")) {
      $("opsNotifyTelegramEnabled").checked =
        String(s.OPS_NOTIFY_TELEGRAM_ENABLED || "false").toLowerCase() === "true";
    }
    if ($("opsNotifyTgToken")) {
      tgTokenConfigured =
        String(s.OPS_NOTIFY_TELEGRAM_BOT_TOKEN_CONFIGURED || "").toLowerCase() === "true" ||
        Boolean((s.OPS_NOTIFY_TELEGRAM_BOT_TOKEN || "").trim());
      $("opsNotifyTgToken").value = tgTokenConfigured ? "••••••••" : "";
      $("opsNotifyTgToken").placeholder = tgTokenConfigured
        ? "•••••••• (сохранён — введите новый чтобы заменить)"
        : "токен бота";
    }
    if ($("opsNotifyTgChat")) {
      $("opsNotifyTgChat").value = s.OPS_NOTIFY_TELEGRAM_CHAT_ID || "";
    }
    if ($("opsNotifyOnReply")) {
      $("opsNotifyOnReply").checked =
        String(s.OPS_NOTIFY_ON_POSITIVE_REPLY || "true").toLowerCase() !== "false";
    }
    if ($("opsNotifyOnPause")) {
      $("opsNotifyOnPause").checked =
        String(s.OPS_NOTIFY_ON_MAILBOX_PAUSE || "true").toLowerCase() !== "false";
    }
    if ($("opsNotifyOnCallback")) {
      $("opsNotifyOnCallback").checked =
        String(s.OPS_NOTIFY_ON_CALLBACK || "true").toLowerCase() !== "false";
    }
    if ($("opsNotifyOncallEnabled")) {
      $("opsNotifyOncallEnabled").checked =
        String(s.OPS_NOTIFY_ONCALL_ENABLED || "false").toLowerCase() === "true";
    }
    if ($("opsNotifyOncallUrl")) {
      $("opsNotifyOncallUrl").value = s.OPS_NOTIFY_ONCALL_WEBHOOK_URL || "";
    }
    if ($("localWindowsHint")) {
      const on = $("localWindowsEnabled") && $("localWindowsEnabled").checked;
      $("localWindowsHint").textContent = on
        ? `Слоты: ${$("localSlots").value || "—"}. Без timezone у компании → ${$("localDefaultTz").value || "Europe/Moscow"}.`
        : "Локальные окна выключены — используется legacy-окно по Москве (ниже).";
    }

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
    if ($("letterCallbackCta")) {
      $("letterCallbackCta").checked =
        String(s.CALLBACK_CTA_ENABLED || "true").toLowerCase() !== "false";
    }
    selectedPackId = s.OUTREACH_SEQUENCE_PACK || selectedPackId || "";
    if (selectedPackId) {
      refreshPresentationMeta(selectedPackId).catch(() => {});
    } else if ($("letterPdfMeta") && s.OUTREACH_PRESENTATION_PDF) {
      $("letterPdfMeta").textContent = `Файл презентации: ${s.OUTREACH_PRESENTATION_PDF}`;
    }
    if (!$("letterTestTo").value && s.MAIL_USERNAME) {
      $("letterTestTo").value = s.MAIL_USERNAME;
    }
    refreshSignatureLive();
  }

  async function loadConsentLedger() {
    if (!$("consentBody")) return;
    const data = await api("/api/modules/consent/ledger?limit=60");
    $("consentBody").innerHTML = (data.items || [])
      .map(
        (r) => `<tr>
        <td class="cell-narrow">${escapeHtml((r.created_at || "").slice(0, 16))}</td>
        <td class="cell-wide">${escapeHtml(r.email || "")}</td>
        <td class="cell-narrow">${escapeHtml(r.status || "")}</td>
        <td class="cell-narrow">${escapeHtml(r.source || "")}</td>
        <td class="cell-wide">${escapeHtml(r.reason || "")}</td>
      </tr>`
      )
      .join("");
    if ($("consentLog") && data.counts) {
      $("consentLog").textContent = `Всего записей: ${data.counts.total || 0}`;
    }
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
    try {
      const geo = await api("/api/modules/clients/geo");
      if ($("clientsGeoStats")) {
        $("clientsGeoStats").innerHTML = [
          ["С городом", geo.with_city || 0],
          ["С timezone", geo.with_timezone || 0],
          ["С обращением", geo.with_director_greeting || 0],
          ["Всего компаний", geo.companies || 0],
        ]
          .map(([l, n]) => `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`)
          .join("");
      }
    } catch (_) {
      /* ignore */
    }
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
        <td class="cell-wide">${escapeHtml(r.email || "")}</td>
        <td class="cell-wide">${escapeHtml(r.display_name || r.director_greeting || "")}</td>
        <td class="cell-city">${escapeHtml(r.city || "—")}</td>
        <td class="cell-tz">${escapeHtml(r.timezone || "—")}</td>
        <td class="cell-narrow">${escapeHtml(r.source || "")}</td>
        <td class="cell-narrow">${companyLink(r.company_bitrix_id, r.company_bitrix_id)}</td>
      </tr>`
      )
      .join("");
  }

  function inboxClassBadge(cls) {
    const c = String(cls || "").toLowerCase();
    const map = {
      positive: "ok",
      positive_interest: "ok",
      human: "ok",
      human_unclassified: "ok",
      interested: "ok",
      negative: "bad",
      unsub: "bad",
      unsubscribe: "bad",
      bounce: "bad",
      ooo: "warn",
      out_of_office: "warn",
      auto: "muted",
      automatic: "muted",
      forward: "warn",
      forwarded: "warn",
    };
    const tone = map[c] || "muted";
    return `<span class="eng ${tone}">${escapeHtml(cls || "—")}</span>`;
  }

  function filterOutboxItems(items) {
    const f = ($("outboxFilter") && $("outboxFilter").value) || "";
    if (!f) return items;
    if (f === "in_window") return items.filter((r) => r.in_window);
    if (f === "outside_window") return items.filter((r) => !r.in_window);
    if (f === "no_tz") return items.filter((r) => !r.timezone && !r.timezone_raw);
    return items;
  }

  function outboxSelectedIds() {
    return Array.from(document.querySelectorAll(".outbox-pick:checked")).map((el) =>
      Number(el.getAttribute("data-id"))
    );
  }

  function updateOutboxBulkBar() {
    const ids = outboxSelectedIds();
    const bar = $("outboxBulkBar");
    const count = $("outboxBulkCount");
    if (!bar) return;
    if (ids.length) {
      bar.classList.remove("hidden");
      if (count) count.textContent = `Выбрано: ${ids.length}`;
    } else {
      bar.classList.add("hidden");
    }
  }

  async function runOutboxBulk(action) {
    const ids = outboxSelectedIds();
    if (!ids.length) return;
    const label = { skip: "пропустить", stop: "остановить цепочки", send_now: "отправить сейчас" }[action];
    if (!confirm(`${label} для ${ids.length} строк?`)) return;
    const data = await api("/api/outbox/bulk", {
      method: "POST",
      body: JSON.stringify({ ids, action }),
    });
    logAction(data);
    await loadOutbox();
    updateOutboxBulkBar();
  }

  function outboxRowActions(r) {
    if (r.status !== "pending") return `<span class="muted">—</span>`;
    const email = escapeHtml(r.email || "");
    const cid = escapeHtml(r.company_id || "");
    return `<div class="row-actions">
      <button type="button" class="small primary" data-action="send-now" data-id="${r.id}" data-email="${email}" title="Игнор локального окна">Сейчас</button>
      <button type="button" class="small ghost" data-action="skip" data-id="${r.id}">Skip</button>
      <button type="button" class="small ghost" data-action="stop" data-email="${email}" data-company="${cid}">Стоп</button>
    </div>`;
  }

  function renderOutboxTable(items, total) {
    const fmtCity = (r) => escapeHtml((r && r.city) || "—");
    const fmtTimezone = (r) => {
      const tz = ((r && r.timezone) || (r && r.timezone_raw) || "").trim();
      return escapeHtml(tz || "—");
    };
    const fmtWindow = (r) => {
      const label = ((r && r.window_label) || "").trim() || "—";
      const cls = r && r.in_window ? "win-now" : "win-later";
      return `<span class="win-badge ${cls}">${escapeHtml(label)}</span>`;
    };
    const filtered = filterOutboxItems(items);
    const missingTz = items.filter((r) => !r.timezone && !r.timezone_raw).length;
    const inWin = items.filter((r) => r.in_window).length;
    const outWin = items.length - inWin;
    const statusVal = ($("outboxStatus") && $("outboxStatus").value) || "";
    if ($("outboxMeta")) {
      let meta = `Показано ${filtered.length} из ${items.length} (всего ${total})`;
      if (!statusVal || statusVal === "pending") {
        meta += ` · в окне: ${inWin} · вне окна: ${outWin}`;
      }
      if (missingTz && statusVal === "pending") {
        meta += ` · без TZ: ${missingTz}`;
      }
      $("outboxMeta").textContent = meta;
    }
    if ($("outboxBody")) {
      $("outboxBody").innerHTML = filtered.length
        ? filtered
            .map(
              (r) => `<tr>
          <td class="cell-check">${
            r.status === "pending"
              ? `<input type="checkbox" class="outbox-pick" data-id="${r.id}" />`
              : `<span class="muted">·</span>`
          }</td>
          <td>${r.id}</td>
          <td class="cell-wide">${escapeHtml(r.email)}</td>
          <td class="cell-wide">${escapeHtml(r.contact_name || r.director_greeting || "")}</td>
          <td class="cell-narrow">${companyLink(r.company_id, r.company_id)}</td>
          <td class="cell-city">${fmtCity(r)}</td>
          <td class="cell-tz">${fmtTimezone(r)}</td>
          <td class="cell-win">${fmtWindow(r)}</td>
          <td class="cell-narrow">${escapeHtml(r.status)}</td>
          <td class="cell-narrow">${escapeHtml(r.sent_at || "")}</td>
          <td class="cell-actions">${outboxRowActions(r)}</td>
        </tr>`
            )
            .join("")
        : `<tr><td colspan="11" class="muted">Нет строк по фильтру</td></tr>`;
    }
    updateOutboxBulkBar();
  }

  function captureBatchMeta(result) {
    if (!result || result.deferred_window_count == null) return;
    lastBatchMeta = {
      deferred_window_count: result.deferred_window_count,
      at: new Date().toISOString(),
    };
    updateQueueDeferHint();
  }

  function updateQueueDeferHint() {
    const el = $("queueDeferHint");
    if (!el) return;
    const parts = [];
    if (lastBatchMeta.deferred_window_count != null) {
      parts.push(
        `Последняя пачка: отложено по локальному окну — ${lastBatchMeta.deferred_window_count}`
      );
    }
    el.textContent = parts.join(" · ");
  }

  function rerenderOutboxFromCache() {
    renderOutboxTable(outboxItemsCache, outboxTotalCache);
  }

  function bucketQueueCalendar(queue, days = 14) {
    const buckets = new Map();
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    for (let i = 0; i < days; i++) {
      const d = new Date(today);
      d.setDate(today.getDate() + i);
      buckets.set(d.toISOString().slice(0, 10), []);
    }
    const pickDate = (iso) => {
      if (!iso) return null;
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return null;
      return d.toISOString().slice(0, 10);
    };
    const add = (item, iso) => {
      const key = pickDate(iso) || today.toISOString().slice(0, 10);
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(item);
    };
    (queue.followups_due || []).forEach((r) => add(r, r.next_action_at));
    (queue.followups_upcoming || []).forEach((r) => add(r, r.next_action_at));
    (queue.first_touch || []).forEach((r) => add(r, r.next_slot_at));
    return buckets;
  }

  function renderQueueCalendar(queue) {
    const box = $("queueCalendar");
    if (!box) return;
    const buckets = bucketQueueCalendar(queue, 14);
    const fmtDay = (key) => {
      try {
        const d = new Date(key + "T12:00:00");
        return d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "short" });
      } catch (_) {
        return key;
      }
    };
    box.innerHTML = Array.from(buckets.entries())
      .map(([day, items]) => {
        const dueN = items.filter((x) => x.due !== false).length;
        const sample = items
          .slice(0, 4)
          .map(
            (r) =>
              `<li>${escapeHtml(r.email || "")} · ${escapeHtml(
                String(r.next_step || r.next_label || "")
              )}</li>`
          )
          .join("");
        const more = items.length > 4 ? `<li class="muted">+${items.length - 4} ещё</li>` : "";
        return `<div class="cal-day ${dueN ? "cal-day-due" : ""}">
          <div class="cal-day-head"><strong>${escapeHtml(fmtDay(day))}</strong><span>${items.length}</span></div>
          <ul class="cal-day-list">${sample || "<li class='muted'>—</li>"}${more}</ul>
        </div>`;
      })
      .join("");
  }

  function renderQueueCalendarFromApi(cal) {
    const box = $("queueCalendar");
    if (!box) return;
    const days = (cal && cal.calendar) || [];
    const fmtDay = (key) => {
      try {
        const d = new Date(key + "T12:00:00");
        return d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "short" });
      } catch (_) {
        return key;
      }
    };
    if (!days.length) {
      box.innerHTML = `<p class="muted tight">Нет данных календаря</p>`;
      return;
    }
    const totals = (cal && cal.totals) || {};
    const meta =
      totals.items != null
        ? `<p class="muted tight">Всего ${totals.items} · due ${totals.due || 0} · дней с задачами ${totals.days_with_items || 0} (${cal.timezone || "Europe/Moscow"})</p>`
        : "";
    box.innerHTML =
      meta +
      days
        .map((day) => {
          const items = day.items || [];
          const dueN = day.due_count || 0;
          const sample = items
            .slice(0, 4)
            .map(
              (r) =>
                `<li>${escapeHtml(r.email || "")} · ${escapeHtml(
                  String(r.next_step || r.next_label || "")
                )}</li>`
            )
            .join("");
          const more =
            day.truncated || items.length > 4
              ? `<li class="muted">+${Math.max(0, (day.count || items.length) - 4)} ещё</li>`
              : "";
          return `<div class="cal-day ${dueN ? "cal-day-due" : ""}">
          <div class="cal-day-head"><strong>${escapeHtml(fmtDay(day.date))}</strong><span>${day.count || 0}</span></div>
          <ul class="cal-day-list">${sample || "<li class='muted'>—</li>"}${more}</ul>
        </div>`;
        })
        .join("");
  }

  async function loadQueueView() {
    const qEl = $("outboxQ");
    const statusEl = $("outboxStatus");
    const q = qEl ? qEl.value.trim() : "";
    const status = statusEl ? statusEl.value : "pending";

    let queue = { first_touch: [], followups_due: [], followups_upcoming: [], counts: {}, send_order_ru: "" };
    try {
      queue = await api("/api/modules/sequences/queue?limit=100");
    } catch (e) {
      logAction(e);
    }

    if ($("queueOrderHint") && queue.send_order_ru) {
      $("queueOrderHint").textContent = queue.send_order_ru;
    }
    const c = queue.counts || {};
    if ($("queueStats")) {
      $("queueStats").innerHTML = `
        <div class="stat"><div class="n">${c.followups_due || 0}</div><div class="l">Due цепочка</div></div>
        <div class="stat"><div class="n">${c.followups_upcoming || 0}</div><div class="l">Скоро</div></div>
        <div class="stat"><div class="n">${c.first_touch_pending_total != null ? c.first_touch_pending_total : (c.first_touch_pending || 0)}</div><div class="l">Первые</div></div>
        <div class="stat"><div class="n">${c.first_touch_in_window != null ? c.first_touch_in_window : "—"}</div><div class="l">В окне сейчас</div></div>
        <div class="stat"><div class="n">${(c.sequences && c.sequences.active) || 0}</div><div class="l">Активных цепочек</div></div>`;
    }
    try {
      const cal = await api("/api/modules/sequences/calendar?days=14");
      renderQueueCalendarFromApi(cal);
    } catch (_) {
      renderQueueCalendar(queue);
    }

    const fmtCity = (r) => escapeHtml((r && r.city) || "—");
    const fmtTimezone = (r) => {
      const tz = ((r && r.timezone) || (r && r.timezone_raw) || "").trim();
      return escapeHtml(tz || "—");
    };
    const fmtWindow = (r) => {
      const label = ((r && r.window_label) || "").trim() || "—";
      const cls = r && r.in_window ? "win-now" : "win-later";
      return `<span class="win-badge ${cls}">${escapeHtml(label)}</span>`;
    };
    const fmtWhen = (iso) => {
      if (!iso) return "сейчас";
      try {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return escapeHtml(String(iso));
        return escapeHtml(d.toLocaleString("ru-RU", { timeZone: "Europe/Moscow" }));
      } catch (_) {
        return escapeHtml(String(iso));
      }
    };

    if ($("queueDueBody")) {
      const due = queue.followups_due || [];
      $("queueDueBody").innerHTML = due.length
        ? due
            .map(
              (r) => `<tr>
            <td class="cell-narrow">${escapeHtml(r.next_step || "—")}</td>
            <td class="cell-narrow">${fmtWhen(r.next_action_at)}</td>
            <td class="cell-wide">${escapeHtml(r.contact_name || "—")}<br><span class="muted">${escapeHtml(r.email || "")}</span></td>
            <td class="cell-city">${fmtCity(r)}</td>
            <td class="cell-tz">${fmtTimezone(r)}</td>
            <td class="cell-win">${fmtWindow(r)}</td>
            <td class="cell-wide">${escapeHtml(r.next_subject || "")}</td>
          </tr>`
            )
            .join("")
        : `<tr><td colspan="7" class="muted">Нет due follow-up — сегодня уйдут только новые первые письма (если Старт).</td></tr>`;
    }

    if ($("queueUpcomingBody")) {
      const up = queue.followups_upcoming || [];
      $("queueUpcomingBody").innerHTML = up.length
        ? up
            .map(
              (r) => `<tr>
            <td>${r.next_step || "—"}</td>
            <td>${fmtWhen(r.next_action_at)}</td>
            <td>${escapeHtml(r.contact_name || "")}<br><span class="muted">${escapeHtml(r.email || "")}</span></td>
            <td class="cell-city">${fmtCity(r)}</td>
            <td class="cell-tz">${fmtTimezone(r)}</td>
            <td class="cell-win">${fmtWindow(r)}</td>
            <td>${escapeHtml(r.next_label || "")}</td>
          </tr>`
            )
            .join("")
        : `<tr><td colspan="7" class="muted">Пока нет запланированных следующих шагов.</td></tr>`;
    }

    const qs = new URLSearchParams({ limit: "100", offset: "0" });
    if (q) qs.set("q", q);
    if (status) qs.set("status", status);
    if (!q && status === "pending") qs.set("sort", "id_asc");
    const data = await api("/api/outbox?" + qs.toString());
    outboxItemsCache = data.items || [];
    outboxTotalCache = data.total != null ? data.total : outboxItemsCache.length;
    renderOutboxTable(outboxItemsCache, outboxTotalCache);
    updateQueueDeferHint();
  }

  async function loadOutbox() {
    await Promise.all([loadQueueView(), loadDash()]);
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
      <div class="stat"><div class="n">${c.total || 0}</div><div class="l">Всего</div></div>
      <div class="stat"><div class="n">${c.unprocessed || 0}</div><div class="l">Необработано</div></div>`;
    $("inboxBody").innerHTML = (data.items || [])
      .map((r) => {
        const btn =
          r.processed == 0
            ? `<button type="button" data-inbox-id="${r.id}">Готово</button>`
            : "";
        return `<tr class="inbox-row" data-inbox-open="${r.id}" style="cursor:pointer">
          <td>${escapeHtml(r.created_at || "")}</td>
          <td>${escapeHtml(r.from_email || "")}</td>
          <td>${inboxClassBadge(r.classification)} <span class="muted">(${Number(r.confidence || 0).toFixed(2)})</span></td>
          <td>${escapeHtml(r.subject || "")}</td>
          <td>${companyLink(r.company_id, r.company_id)}</td>
          <td>${btn}</td>
        </tr>`;
      })
      .join("");
  }

  function activeTabName() {
    const btn = document.querySelector(".tabs button.active");
    return (btn && btn.dataset.tab) || "letter";
  }

  let lprLastRunId = null;

  function statusChip(st) {
    const s = String(st || "proposed");
    const map = {
      proposed: "chip-neutral",
      approved: "chip-ok",
      rejected: "chip-bad",
      cluster_pending: "chip-warn",
      draft: "chip-neutral",
      pending_approval: "chip-warn",
      new: "chip-neutral",
      uploaded_private: "chip-ok",
    };
    return `<span class="ros-chip ${map[s] || "chip-neutral"}">${escapeHtml(s)}</span>`;
  }

  function renderLprCoverage(coverage) {
    const el = $("lprCoverage");
    if (!el) return;
    const roles = (coverage && coverage.roles) || [];
    const missing = (coverage && coverage.missing_roles) || [];
    if (!roles.length) {
      el.innerHTML = `<p class="muted tight">Покрытие появится после поиска.</p>`;
      return;
    }
    el.innerHTML =
      `<div class="lpr-coverage-row">` +
      roles
        .map(
          (r) =>
            `<span class="lpr-role ${r.covered ? "ok" : "miss"}"><span class="lpr-role-id">${escapeHtml(
              r.role_id || ""
            )}</span>${r.covered ? " покрыта" : " нет"}</span>`
        )
        .join("") +
      `</div>` +
      (missing.length
        ? `<p class="muted tight" style="margin-top:0.4rem">Не хватает: ${escapeHtml(missing.join(", "))}</p>`
        : `<p class="muted tight" style="margin-top:0.4rem">Минимальный комитет закрыт.</p>`);
  }

  function renderLprCandidates(items) {
    const box = $("lprCards");
    if (!box) return;
    const list = items || [];
    if (!list.length) {
      box.innerHTML = `<p class="muted tight">Кандидатов нет — уточните company id или добавьте import.</p>`;
      return;
    }
    box.innerHTML = list
      .map((c) => {
        const st = c.status || "proposed";
        const link = c.profile_url
          ? `<a class="ros-link" href="${escapeHtml(c.profile_url)}" target="_blank" rel="noopener">профиль</a>`
          : "";
        let actions = "";
        if (st === "rejected" || st === "merged") {
          actions = `<span class="muted tight">${escapeHtml(st)}</span>`;
        } else {
          const mergeBtn = c.cluster_id
            ? `<button type="button" class="small btn-quiet" data-lpr-merge="${escapeHtml(c.cluster_id)}" data-lpr-keep="${escapeHtml(c.id)}">Слить кластер сюда</button>`
            : "";
          actions = `<div class="ros-card-actions">
                <button type="button" class="small primary" data-lpr-approve="${escapeHtml(c.id)}">Утвердить</button>
                <button type="button" class="small btn-quiet" data-lpr-reject="${escapeHtml(c.id)}">Отклонить</button>
                <button type="button" class="small btn-quiet" data-lpr-task="${escapeHtml(c.id)}">Task</button>
                ${mergeBtn}
              </div>`;
        }
        return `<article class="ros-card">
          <div class="ros-card-head">
            <div>
              <div class="ros-card-title">${escapeHtml(c.full_name || "Без имени")}${
          c.cluster_id ? ' <span class="badge">cluster</span>' : ""
        }</div>
              <div class="muted tight">${escapeHtml(c.role_guess || "роль ?")} · ${escapeHtml(
          c.source || ""
        )} · score ${Number(c.score || 0).toFixed(2)} ${link}</div>
            </div>
            ${statusChip(st)}
          </div>
          ${actions}
        </article>`;
      })
      .join("");
    box.querySelectorAll("[data-lpr-approve]").forEach((btn) => {
      btn.addEventListener("click", () =>
        setLprStatus(btn.getAttribute("data-lpr-approve"), "approved").catch(logAction)
      );
    });
    box.querySelectorAll("[data-lpr-reject]").forEach((btn) => {
      btn.addEventListener("click", () =>
        setLprStatus(btn.getAttribute("data-lpr-reject"), "rejected").catch(logAction)
      );
    });
    box.querySelectorAll("[data-lpr-task]").forEach((btn) => {
      btn.addEventListener("click", () =>
        createLprTask(btn.getAttribute("data-lpr-task")).catch(logAction)
      );
    });
    box.querySelectorAll("[data-lpr-merge]").forEach((btn) => {
      btn.addEventListener("click", () =>
        mergeLprCluster(
          btn.getAttribute("data-lpr-merge"),
          btn.getAttribute("data-lpr-keep")
        ).catch(logAction)
      );
    });
  }

  async function mergeLprCluster(clusterId, keepId) {
    const data = await api(`/api/modules/social/clusters/${encodeURIComponent(clusterId)}/merge`, {
      method: "POST",
      body: JSON.stringify({ keep_candidate_id: keepId }),
    });
    if ($("lprMeta")) {
      $("lprMeta").textContent = `Кластер слит · остался 1 кандидат · merged ${data.merged_count || 0}`;
    }
    if (lprLastRunId) await reloadLprRun(lprLastRunId);
  }

  async function setLprStatus(id, status) {
    await api(`/api/modules/social/candidates/${encodeURIComponent(id)}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
    if (lprLastRunId) await reloadLprRun(lprLastRunId);
  }

  async function createLprTask(id) {
    const data = await api("/api/modules/social/tasks", {
      method: "POST",
      body: JSON.stringify({ candidate_id: id, draft_text: "", action_type: "open_profile" }),
    });
    if ($("lprMeta")) {
      $("lprMeta").textContent = `Task создан · ${((data.task || {}).profile_url) || "без URL"}`;
    }
  }

  async function reloadLprRun(runId) {
    const data = await api(`/api/modules/social/runs/${encodeURIComponent(runId)}`);
    renderLprCoverage(data.coverage);
    renderLprCandidates(data.candidates || []);
  }

  async function loadLprTab() {
    if ($("lprMeta") && !$("lprMeta").textContent) {
      $("lprMeta").textContent = "Укажите company id или import и нажмите «Найти кандидатов».";
    }
  }

  async function runLprSearch() {
    const imports = [];
    const webUrl = (($("lprWebUrl") && $("lprWebUrl").value) || "").trim();
    if (webUrl) {
      imports.push({
        source: "web_import",
        profile_url: webUrl,
        full_name: ($("lprWebName") && $("lprWebName").value) || "",
      });
    }
    const tg = (($("lprTgUser") && $("lprTgUser").value) || "").trim().replace(/^@/, "");
    if (tg) {
      imports.push({
        source: "telegram",
        username: tg,
        full_name: ($("lprTgName") && $("lprTgName").value) || "",
      });
    }
    const payload = {
      bitrix_company_id: (($("lprCompanyId") && $("lprCompanyId").value) || "").trim() || null,
      company_title: (($("lprCompanyTitle") && $("lprCompanyTitle").value) || "").trim(),
      inn: (($("lprInn") && $("lprInn").value) || "").trim() || null,
      sources: ["clients", "dadata", "web_import", "telegram"],
      imports,
    };
    if ($("lprMeta")) $("lprMeta").textContent = "Ищем…";
    const data = await api("/api/modules/social/search", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    lprLastRunId = (data.run && data.run.id) || null;
    renderLprCoverage(data.coverage);
    renderLprCandidates(data.candidates || []);
    if ($("lprMeta")) {
      const n = (data.candidates || []).length;
      const miss = ((data.coverage && data.coverage.missing_roles) || []).length;
      $("lprMeta").textContent = `${n} кандидат(ов) · cost ${
        (data.run && data.run.cost_estimate) || 0
      } · незакрытых ролей: ${miss}`;
    }
  }

  async function loadLprCaps() {
    const data = await api("/api/modules/social/capabilities");
    const items = data.items || [];
    if ($("lprMeta")) {
      $("lprMeta").textContent = items
        .map((c) => `${c.source_id}${c.search ? " (search)" : " (import)"}`)
        .join(" · ");
    }
  }

  function bindStudioSubTabs() {
    document.querySelectorAll(".sub-tab[data-studio-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".sub-tab[data-studio-view]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const view = btn.dataset.studioView;
        const content = $("studioViewContent");
        const radar = $("studioViewRadar");
        const video = $("studioViewVideo");
        if (content) content.hidden = view !== "content";
        if (radar) radar.hidden = view !== "radar";
        if (video) video.hidden = view !== "video";
        if (view === "content") loadContentDrafts().catch(logAction);
        if (view === "radar") loadRadarSignals().catch(logAction);
        if (view === "video") loadVideoDrafts().catch(logAction);
      });
    });
  }

  async function loadStudioTab() {
    bindStudioSubTabs();
    const active = document.querySelector(".sub-tab[data-studio-view].active");
    const view = (active && active.dataset.studioView) || "content";
    if (view === "content") await loadContentDrafts();
    else if (view === "radar") await loadRadarSignals();
    else await loadVideoDrafts();
  }

  function renderContentCards(items) {
    const box = $("csCards");
    if (!box) return;
    const list = items || [];
    if (!list.length) {
      box.innerHTML = `<p class="muted tight">Пока пусто — создайте черновик слева.</p>`;
      return;
    }
    box.innerHTML = list
      .map((d) => {
        const letters = ((d.body && d.body.letters) || []).length;
        const actions =
          d.status === "approved"
            ? `<span class="muted tight">утверждён</span>`
            : `<button type="button" class="small primary" data-cs-approve="${escapeHtml(d.id)}">Утвердить</button>
               <button type="button" class="small btn-quiet" data-cs-reject="${escapeHtml(d.id)}">Отклонить</button>`;
        return `<article class="ros-card">
          <div class="ros-card-head">
            <div>
              <div class="ros-card-title">${escapeHtml(d.title || "Черновик")}</div>
              <div class="muted tight">${escapeHtml(d.industry_pack || "")} · ${letters} писем · ${escapeHtml(
          (d.objection || "").slice(0, 80)
        )}</div>
            </div>
            ${statusChip(d.status)}
          </div>
          <div class="ros-card-actions">${actions}</div>
        </article>`;
      })
      .join("");
    box.querySelectorAll("[data-cs-approve]").forEach((btn) => {
      btn.addEventListener("click", () =>
        setContentStatus(btn.getAttribute("data-cs-approve"), "approved").catch(logAction)
      );
    });
    box.querySelectorAll("[data-cs-reject]").forEach((btn) => {
      btn.addEventListener("click", () =>
        setContentStatus(btn.getAttribute("data-cs-reject"), "rejected").catch(logAction)
      );
    });
  }

  async function setContentStatus(id, status) {
    await api(`/api/modules/content_studio/drafts/${encodeURIComponent(id)}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
    await loadContentDrafts();
  }

  async function loadContentDrafts() {
    const data = await api("/api/modules/content_studio/drafts?limit=30");
    renderContentCards(data.items || []);
  }

  async function createContentDraft() {
    const objection = (($("csObjection") && $("csObjection").value) || "").trim();
    if (!objection) throw new Error("Укажите возражение");
    await api("/api/modules/content_studio/drafts", {
      method: "POST",
      body: JSON.stringify({
        objection,
        industry_pack: ($("csPack") && $("csPack").value) || "lombards",
      }),
    });
    if ($("csObjection")) $("csObjection").value = "";
    await loadContentDrafts();
  }

  function renderRadarCards(items) {
    const box = $("radarCards");
    if (!box) return;
    const list = items || [];
    if (!list.length) {
      box.innerHTML = `<p class="muted tight">Сигналов пока нет.</p>`;
      return;
    }
    box.innerHTML = list
      .map((s) => {
        return `<article class="ros-card">
          <div class="ros-card-head">
            <div>
              <div class="ros-card-title">${escapeHtml(s.company_title || s.signal_type || "Сигнал")}</div>
              <div class="muted tight">${escapeHtml(s.signal_type || "")} · score ${Number(
          s.score || 0
        ).toFixed(2)} · ${escapeHtml((s.summary || "").slice(0, 100))}</div>
            </div>
            ${statusChip(s.status)}
          </div>
          <div class="ros-card-actions">
            <button type="button" class="small primary" data-radar-verify="${escapeHtml(s.id)}">Проверить</button>
            <button type="button" class="small btn-quiet" data-radar-dismiss="${escapeHtml(s.id)}">Скрыть</button>
          </div>
        </article>`;
      })
      .join("");
    box.querySelectorAll("[data-radar-verify]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-radar-verify");
        const data = await api(`/api/modules/radar/signals/${encodeURIComponent(id)}/verify`, {
          method: "POST",
          body: "{}",
        });
        btn.textContent = (data.suggested_action || "ok").replace(/_/g, " ");
      });
    });
    box.querySelectorAll("[data-radar-dismiss]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api(`/api/modules/radar/signals/${encodeURIComponent(btn.getAttribute("data-radar-dismiss"))}/status`, {
          method: "POST",
          body: JSON.stringify({ status: "dismissed" }),
        });
        await loadRadarSignals();
      });
    });
  }

  async function loadRadarSignals() {
    const data = await api("/api/modules/radar/signals?limit=40");
    renderRadarCards(data.items || []);
  }

  async function ingestRadarSignal() {
    const summary = (($("radarSummary") && $("radarSummary").value) || "").trim();
    if (!summary) throw new Error("Укажите краткое описание");
    await api("/api/modules/radar/signals", {
      method: "POST",
      body: JSON.stringify({
        signal_type: ($("radarType") && $("radarType").value) || "manual",
        company_title: ($("radarCompany") && $("radarCompany").value) || "",
        summary,
        score: Number(($("radarScore") && $("radarScore").value) || 0.5),
      }),
    });
    if ($("radarSummary")) $("radarSummary").value = "";
    await loadRadarSignals();
  }

  function renderVideoCards(items) {
    const box = $("videoCards");
    if (!box) return;
    const list = items || [];
    if (!list.length) {
      box.innerHTML = `<p class="muted tight">Создайте первый черновик слева.</p>`;
      return;
    }
    box.innerHTML = list
      .map((d) => {
        const actions =
          d.status === "approved"
            ? `<button type="button" class="small primary" data-video-upload="${escapeHtml(d.id)}">Private upload</button>`
            : d.status === "uploaded_private"
              ? `<span class="muted tight">private queue</span>`
              : `<button type="button" class="small primary" data-video-approve="${escapeHtml(d.id)}">Утвердить</button>
                 <button type="button" class="small btn-quiet" data-video-reject="${escapeHtml(d.id)}">Отклонить</button>`;
        return `<article class="ros-card">
          <div class="ros-card-head">
            <div>
              <div class="ros-card-title">${escapeHtml(d.title || "Video")}</div>
              <div class="muted tight">${escapeHtml((d.brief || "").slice(0, 100))}</div>
            </div>
            ${statusChip(d.status)}
          </div>
          <div class="ros-card-actions">${actions}</div>
        </article>`;
      })
      .join("");
    box.querySelectorAll("[data-video-approve]").forEach((btn) => {
      btn.addEventListener("click", () =>
        setVideoStatus(btn.getAttribute("data-video-approve"), "approved").catch(logAction)
      );
    });
    box.querySelectorAll("[data-video-reject]").forEach((btn) => {
      btn.addEventListener("click", () =>
        setVideoStatus(btn.getAttribute("data-video-reject"), "rejected").catch(logAction)
      );
    });
    box.querySelectorAll("[data-video-upload]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api(
          `/api/modules/video_studio/drafts/${encodeURIComponent(btn.getAttribute("data-video-upload"))}/queue-private-upload`,
          { method: "POST", body: "{}" }
        );
        await loadVideoDrafts();
      });
    });
  }

  async function setVideoStatus(id, status) {
    await api(`/api/modules/video_studio/drafts/${encodeURIComponent(id)}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
    await loadVideoDrafts();
  }

  async function loadVideoDrafts() {
    const data = await api("/api/modules/video_studio/drafts?limit=30");
    renderVideoCards(data.items || []);
  }

  async function createVideoDraft() {
    const title = (($("videoTitle") && $("videoTitle").value) || "").trim();
    if (!title) throw new Error("Укажите название");
    await api("/api/modules/video_studio/drafts", {
      method: "POST",
      body: JSON.stringify({
        title,
        brief: ($("videoBrief") && $("videoBrief").value) || "",
        script_text: ($("videoScript") && $("videoScript").value) || "",
      }),
    });
    if ($("videoTitle")) $("videoTitle").value = "";
    if ($("videoBrief")) $("videoBrief").value = "";
    if ($("videoScript")) $("videoScript").value = "";
    await loadVideoDrafts();
  }


  function refreshActiveTab() {
    const tab = activeTabName();
    if (tab === "clients") loadClients().catch((e) => ($("clientsLog").textContent = String(e)));
    else if (tab === "lpr") loadLprTab().catch((e) => { if ($("lprMeta")) $("lprMeta").textContent = String(e); });
    else if (tab === "studio") loadStudioTab().catch(logAction);
    else if (tab === "outbox") loadOutbox().catch(logAction);
    else if (tab === "inbox") {
      const view = document.querySelector(".sub-tab.active");
      if (view && view.dataset.inboxView === "replies") loadReplies().catch(logAction);
      else loadInbox(true).catch(logAction);
    } else if (tab === "report") loadReport().catch(logAction);
    else if (tab === "settings") {
      loadSettingsIntoForms()
        .then(() => Promise.all([loadAntiban(), loadConsentLedger(), loadIntegrationsHealth()]))
        .catch((e) => {
          if ($("antibanLog")) $("antibanLog").textContent = String(e);
          logAction(e);
        });
    } else if (tab === "letter") {
      loadSettingsIntoForms()
        .then(() => loadPacks())
        .catch(logAction);
    }
  }

  function bindInboxSubTabs() {
    document.querySelectorAll(".sub-tab[data-inbox-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".sub-tab[data-inbox-view]").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const view = btn.dataset.inboxView;
        const classified = $("inboxViewClassified");
        const replies = $("inboxViewReplies");
        if (view === "replies") {
          if (classified) classified.hidden = true;
          if (replies) replies.hidden = false;
          loadReplies().catch(logAction);
        } else {
          if (classified) classified.hidden = false;
          if (replies) replies.hidden = true;
          loadInbox(true).catch(logAction);
        }
      });
    });
  }

  function bindTabs() {
    bindInboxSubTabs();
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
        if (tab === "lpr") loadLprTab().catch((e) => { if ($("lprMeta")) $("lprMeta").textContent = String(e); });
        if (tab === "studio") loadStudioTab().catch(logAction);
        if (tab === "outbox") loadOutbox().catch(logAction);
        if (tab === "report") loadReport().catch(logAction);
        if (tab === "settings") {
          loadSettingsIntoForms()
            .then(() => Promise.all([loadAntiban(), loadConsentLedger(), loadIntegrationsHealth()]))
            .catch((e) => {
              if ($("antibanLog")) $("antibanLog").textContent = String(e);
              logAction(e);
            });
        }
        if (tab === "letter") {
          loadSettingsIntoForms()
            .then(() => loadPacks())
            .catch(logAction);
        }
        if (tab === "inbox") {
          const sub = document.querySelector('.sub-tab[data-inbox-view="classified"]');
          if (sub) sub.click();
          else loadInbox(true).catch(logAction);
        }
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
    if ($("lprSearchBtn")) {
      $("lprSearchBtn").addEventListener("click", () => runLprSearch().catch((e) => {
        if ($("lprMeta")) $("lprMeta").textContent = String(e);
      }));
    }
    if ($("lprCapsBtn")) {
      $("lprCapsBtn").addEventListener("click", () => loadLprCaps().catch((e) => {
        if ($("lprMeta")) $("lprMeta").textContent = String(e);
      }));
    }
    if ($("csDraftBtn")) {
      $("csDraftBtn").addEventListener("click", () => createContentDraft().catch(logAction));
    }
    if ($("csListBtn")) {
      $("csListBtn").addEventListener("click", () => loadContentDrafts().catch(logAction));
    }
    if ($("radarIngestBtn")) {
      $("radarIngestBtn").addEventListener("click", () => ingestRadarSignal().catch(logAction));
    }
    if ($("radarListBtn")) {
      $("radarListBtn").addEventListener("click", () => loadRadarSignals().catch(logAction));
    }
    if ($("videoDraftBtn")) {
      $("videoDraftBtn").addEventListener("click", () => createVideoDraft().catch(logAction));
    }
    if ($("videoListBtn")) {
      $("videoListBtn").addEventListener("click", () => loadVideoDrafts().catch(logAction));
    }
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
      loadDash()
        .then(() => refreshActiveTab())
        .catch(logAction);
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
        $("clientsLog").textContent = "Скачиваю Bitrix + geo/ФИО…";
        const data = await api("/sync", { method: "POST", body: "{}" });
        const geo = data.geo_backfill || {};
        const stats = geo.stats || {};
        $("clientsLog").textContent =
          JSON.stringify(data, null, 2) +
          (stats.with_timezone != null
            ? `\n\nGeo: TZ ${stats.with_timezone}/${stats.companies || "?"} · updated ${geo.updated || 0}`
            : "");
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
    if ($("clientsBackfillGeoBtn")) {
      $("clientsBackfillGeoBtn").addEventListener("click", async () => {
        try {
          $("clientsLog").textContent = "Дотягиваю city / timezone / ФИО…";
          const data = await api("/api/modules/clients/backfill-geo", {
            method: "POST",
            body: "{}",
          });
          $("clientsLog").textContent = JSON.stringify(data, null, 2);
          await loadClients();
          await loadDash();
        } catch (e) {
          $("clientsLog").textContent = String(e);
        }
      });
    }
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
        const result = await api("/send-batch", {
          method: "POST",
          body: JSON.stringify({ limit: 5, dry_run: true }),
        });
        captureBatchMeta(result);
        logAction(result);
      } catch (e) {
        logAction(String(e));
      }
    });
    $("sendBtn").addEventListener("click", async () => {
      const n = Number($("sendN").value || 1);
      if (!confirm(`Отправить ${n} писем из очереди сейчас? Нужен статус «Идёт» (Старт).`)) return;
      try {
        const result = await api("/send-batch", {
          method: "POST",
          body: JSON.stringify({ limit: n, dry_run: false }),
        });
        captureBatchMeta(result);
        logAction(result);
        await loadDash();
        await loadOutbox();
      } catch (e) {
        logAction(String(e));
      }
    });

    function campaignSettingsPayload() {
      readLetterFormIntoChain();
      const step1 = letterChain[0] || {};
      return {
        OUTREACH_SUBJECT: step1.subject || ($("letterSubject") && $("letterSubject").value) || "",
        OUTREACH_COMPANY_NAME: $("letterCompany").value,
        OUTREACH_WEBSITE: $("letterWebsite").value,
        OUTREACH_CONTACT_PHONE: $("letterPhone").value,
        OUTREACH_CONTACT_EMAIL: $("letterEmail") ? $("letterEmail").value : "",
        OUTREACH_SIGNATURE: $("letterSignature") ? $("letterSignature").value : "",
        OUTREACH_LOGO_URL: ($("letterLogoPreview") && $("letterLogoPreview").getAttribute("src")) || "",
        OUTREACH_LOGO_ENABLED: $("letterLogoEnabled") && $("letterLogoEnabled").checked ? "true" : "false",
        OUTREACH_TEMPLATE_PLAIN: step1.plain || ($("letterPlain") && $("letterPlain").value) || "",
        OUTREACH_TEMPLATE_HTML: step1.html || ($("letterHtml") && $("letterHtml").value) || "",
        OUTREACH_ATTACH_PRESENTATION: step1.attach_presentation ? "true" : "false",
        CALLBACK_CTA_ENABLED: $("letterCallbackCta") && $("letterCallbackCta").checked ? "true" : "false",
        OUTREACH_SEQUENCE_PACK: selectedPackId || settingsCache?.OUTREACH_SEQUENCE_PACK || "",
        SEQUENCES_ENABLED: "true",
      };
    }

    async function saveCampaignSettings() {
      await applyCampaignContacts({ quiet: true });
      const chain = await saveLetterChain();
      const data = await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ settings: campaignSettingsPayload() }),
      });
      if (data.settings) settingsCache = data.settings;
      return { ...(data || {}), pack: chain && chain.pack };
    }

    function formatSendOneResult(data, dry) {
      const attached = data.attached || (data.results && data.results[0] && data.results[0].attached) || [];
      const to =
        (data.results && data.results[0] && data.results[0].email) ||
        ($("letterTestTo") && $("letterTestTo").value) ||
        "";
      const pdf = attached.length ? `Вложение: ${attached.join(", ")}` : "Без PDF";
      const used = data.oneshot_today != null ? ` · тестов сегодня: ${data.oneshot_today}/${data.oneshot_daily_limit || 25}` : "";
      if (dry) {
        return `Превью SMTP для ${to}: ок. ${pdf}${used}`;
      }
      return `Тест отправлен на ${to}. ${pdf}${used}`;
    }

    async function doSendOne(dry, opts = {}) {
      const toEl = opts.toId ? $(opts.toId) : $("letterTestTo");
      const nameEl = opts.nameId ? $(opts.nameId) : $("letterTestName");
      const logEl = opts.logId ? $(opts.logId) : null;
      const to = ((toEl && toEl.value) || "").trim();
      if (!to) {
        const msg = "Укажите email в поле «Кому»";
        if (logEl) {
          logEl.hidden = false;
          logEl.textContent = msg;
        }
        logAction(msg);
        return;
      }
      if (!dry && !confirm(`Отправить тестовое письмо на ${to}?`)) return;
      try {
        if (opts.saveFirst) {
          await saveCampaignSettings();
        }
        const attach =
          $("letterAttachPdf") != null ? !!$("letterAttachPdf").checked : null;
        const data = await api("/send-one", {
          method: "POST",
          body: JSON.stringify({
            to,
            contact_name: ((nameEl && nameEl.value) || "").trim() || null,
            dry_run: !!dry,
            create_bitrix_deal: false,
            attach_presentation: attach,
          }),
        });
        const summary = formatSendOneResult(data, dry);
        if (logEl) {
          logEl.hidden = false;
          logEl.textContent = summary;
        }
        logAction(summary);
        logAction(data);
        if (!dry) await loadDash();
      } catch (e) {
        if (logEl) {
          logEl.hidden = false;
          logEl.textContent = String(e);
        }
        logAction(String(e));
      }
    }
    if ($("letterTestSendBtn")) {
      $("letterTestDryBtn").addEventListener("click", () =>
        doSendOne(true, {
          toId: "letterTestTo",
          nameId: "letterTestName",
          logId: "letterLog",
          saveFirst: true,
        })
      );
      $("letterTestSendBtn").addEventListener("click", () =>
        doSendOne(false, {
          toId: "letterTestTo",
          nameId: "letterTestName",
          logId: "letterLog",
          saveFirst: true,
        })
      );
    }

    $("outboxLoad").addEventListener("click", () => loadOutbox().catch(logAction));
    if ($("outboxFilter")) {
      $("outboxFilter").addEventListener("change", () => rerenderOutboxFromCache());
    }
    if ($("queueRebuildNamesBtn")) {
      $("queueRebuildNamesBtn").addEventListener("click", async () => {
        try {
          const data = await api("/api/modules/clients/rebuild-outbox", { method: "POST" });
          logAction(
            `Очередь обновлена: новых ${data.inserted_new || 0}, с ФИО ${data.with_director_name || 0}`
          );
          await loadOutbox();
        } catch (e) {
          logAction(e);
        }
      });
    }
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
        if (btn) {
          ev.stopPropagation();
          try {
            await api("/api/modules/replies/inbox/" + btn.dataset.inboxId + "/processed", {
              method: "POST",
              body: "{}",
            });
            await loadInbox(true);
          } catch (e) {
            logAction(String(e));
          }
          return;
        }
        const row = ev.target.closest("tr[data-inbox-open]");
        if (!row) return;
        if (ev.target.closest(".company-open")) return;
        openInboxThread(row.dataset.inboxOpen).catch(logAction);
      });
    }
    if ($("outboxBody")) {
      $("outboxBody").addEventListener("change", (ev) => {
        if (ev.target && ev.target.classList && ev.target.classList.contains("outbox-pick")) {
          updateOutboxBulkBar();
        }
      });
      $("outboxBody").addEventListener("click", async (ev) => {
        const btn = ev.target.closest("button[data-action]");
        if (!btn) return;
        const action = btn.dataset.action;
        try {
          if (action === "send-now") {
            const email = btn.dataset.email || "";
            if (!email) return;
            if (!confirm(`Отправить сейчас ${email}? Игнорирует локальное окно.`)) return;
            const result = await api("/send-batch", {
              method: "POST",
              body: JSON.stringify({ limit: 1, only_email: email, dry_run: false }),
            });
            captureBatchMeta(result);
            logAction(result);
          } else if (action === "skip") {
            await api("/api/outbox/" + btn.dataset.id, {
              method: "PATCH",
              body: JSON.stringify({ status: "skipped" }),
            });
          } else if (action === "stop") {
            await api("/api/modules/sequences/stop", {
              method: "POST",
              body: JSON.stringify({
                email: btn.dataset.email || "",
                company_id: btn.dataset.company || null,
                reason: "manual",
              }),
            });
          } else {
            return;
          }
          await loadOutbox();
        } catch (e) {
          logAction(String(e));
        }
      });
    }
    if ($("outboxSelectAll")) {
      $("outboxSelectAll").addEventListener("change", (ev) => {
        const on = ev.target.checked;
        document.querySelectorAll(".outbox-pick").forEach((el) => {
          el.checked = on;
        });
        updateOutboxBulkBar();
      });
    }
    ["outboxBulkSend", "outboxBulkSkip", "outboxBulkStop"].forEach((id, idx) => {
      const btn = $(id);
      const action = ["send_now", "skip", "stop"][idx];
      if (btn) {
        btn.addEventListener("click", () => runOutboxBulk(action).catch((e) => logAction(String(e))));
      }
    });

    if ($("opsOncallTest")) {
      $("opsOncallTest").addEventListener("click", async () => {
        try {
          const data = await api("/api/ops/oncall/test", {
            method: "POST",
            body: JSON.stringify({ message: "Quantum Panel · тест on-call webhook" }),
          });
          logAction(data);
        } catch (e) {
          logAction(String(e));
        }
      });
    }

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

    if ($("letterPdfFile")) {
      $("letterPdfFile").addEventListener("change", async () => {
        const file = $("letterPdfFile").files && $("letterPdfFile").files[0];
        const packId =
          selectedPackId ||
          document.querySelector('input[name="packId"]:checked')?.value ||
          "";
        if (!file) return;
        if (!packId) {
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = "Сначала выберите отрасль.";
          }
          $("letterPdfFile").value = "";
          return;
        }
        try {
          const fd = new FormData();
          fd.append("file", file);
          const data = await api("/api/packs/" + encodeURIComponent(packId) + "/presentation", {
            method: "POST",
            body: fd,
          });
          const meta = data.presentation || {};
          if ($("letterPdfMeta")) {
            $("letterPdfMeta").textContent = formatPresentationMeta(meta, packId);
          }
          if ($("letterPdfReset")) $("letterPdfReset").disabled = !meta.can_reset;
          if ($("letterAttachPdf")) $("letterAttachPdf").checked = true;
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent =
              `Презентация для «${packId}» загружена (${formatBytes(meta.bytes || file.size)}).`;
          }
          // refresh pack cache meta
          const pack = packsCache.find((p) => p.id === packId);
          if (pack) pack.presentation_meta = meta;
        } catch (e) {
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = String(e);
          }
        } finally {
          $("letterPdfFile").value = "";
        }
      });
    }
    if ($("letterPdfReset")) {
      $("letterPdfReset").addEventListener("click", async () => {
        const packId =
          selectedPackId ||
          document.querySelector('input[name="packId"]:checked')?.value ||
          "";
        if (!packId) return;
        try {
          const data = await api("/api/packs/" + encodeURIComponent(packId) + "/presentation", {
            method: "DELETE",
          });
          const meta = data.presentation || {};
          if ($("letterPdfMeta")) {
            $("letterPdfMeta").textContent = formatPresentationMeta(meta, packId);
          }
          if ($("letterPdfReset")) $("letterPdfReset").disabled = !meta.can_reset;
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = `Презентация «${packId}» сброшена к базовой.`;
          }
        } catch (e) {
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = String(e);
          }
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
          const hasLocalDraft =
            letterDirty || !!(packsCache.find((p) => p.id === packId) || {}).has_draft;
          let resetDraft = false;
          if (hasLocalDraft) {
            resetDraft = confirm(
              "Сбросить цепочку к базовым письмам отрасли?\n\nОК — базовые тексты.\nОтмена — оставить черновик и просто активировать отрасль."
            );
          }
          const data = await api("/api/packs/apply", {
            method: "POST",
            body: JSON.stringify({
              pack_id: packId,
              reset_draft: !!resetDraft,
            }),
          });
          settingsCache = data.settings || settingsCache;
          await loadSettingsIntoForms();
          renderPackCards(packId);
          if (data.pack) setLetterChainFromPack(data.pack, { fill: true });
          else await previewPack(packId, true);
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent =
              `Применена отрасль «${(data.pack && data.pack.title) || packId}». Цепочка: ${(data.pack && data.pack.steps && data.pack.steps.length) || letterChain.length} писем.`;
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
        const data = await saveCampaignSettings();
        renderPackCards(selectedPackId);
        if ($("letterLog")) {
          $("letterLog").hidden = false;
          $("letterLog").textContent = `Цепочка сохранена (${letterChain.length} писем).`;
        }
        logAction(data);
      } catch (e) {
        if ($("letterLog")) {
          $("letterLog").hidden = false;
          $("letterLog").textContent = String(e);
        }
        logAction(String(e));
      }
    });

    function markLetterDirty() {
      letterDirty = true;
      renderLetterTabs();
    }
    ["letterSubject", "letterPlain", "letterHtml", "letterDelayDays", "letterLabel", "letterAttachPdf"].forEach((id) => {
      const el = $(id);
      if (!el) return;
      el.addEventListener("input", markLetterDirty);
      el.addEventListener("change", markLetterDirty);
    });

    if ($("letterAddBtn")) {
      $("letterAddBtn").addEventListener("click", () => {
        readLetterFormIntoChain();
        letterChain.push(blankLetter());
        activeLetterIdx = letterChain.length - 1;
        letterDirty = true;
        writeLetterFormFromChain();
      });
    }
    if ($("letterDupBtn")) {
      $("letterDupBtn").addEventListener("click", () => {
        readLetterFormIntoChain();
        const src = letterChain[activeLetterIdx] || blankLetter();
        const copy = blankLetter({
          ...src,
          label: (src.label || "letter") + "_copy",
          delay_days: Number(src.delay_days || 0) + 1,
        });
        letterChain.splice(activeLetterIdx + 1, 0, copy);
        activeLetterIdx += 1;
        letterDirty = true;
        writeLetterFormFromChain();
      });
    }
    if ($("letterDelBtn")) {
      $("letterDelBtn").addEventListener("click", () => {
        if (letterChain.length <= 1) return;
        if (!confirm("Удалить текущее письмо из цепочки?")) return;
        readLetterFormIntoChain();
        letterChain.splice(activeLetterIdx, 1);
        if (activeLetterIdx >= letterChain.length) activeLetterIdx = letterChain.length - 1;
        letterDirty = true;
        writeLetterFormFromChain();
      });
    }
    function moveLetter(delta) {
      readLetterFormIntoChain();
      const j = activeLetterIdx + delta;
      if (j < 0 || j >= letterChain.length) return;
      const tmp = letterChain[activeLetterIdx];
      letterChain[activeLetterIdx] = letterChain[j];
      letterChain[j] = tmp;
      activeLetterIdx = j;
      letterDirty = true;
      writeLetterFormFromChain();
    }
    if ($("letterMoveUp")) $("letterMoveUp").addEventListener("click", () => moveLetter(-1));
    if ($("letterMoveDown")) $("letterMoveDown").addEventListener("click", () => moveLetter(1));
    if ($("letterResetChain")) {
      $("letterResetChain").addEventListener("click", async () => {
        const packId = selectedPackId;
        if (!packId) return;
        if (!confirm("Сбросить все письма отрасли к базовым текстам?")) return;
        try {
          const data = await api("/api/packs/" + encodeURIComponent(packId) + "/letters/reset", {
            method: "POST",
            body: "{}",
          });
          if (data.settings) settingsCache = data.settings;
          const idx = packsCache.findIndex((p) => p.id === packId);
          if (idx >= 0) packsCache[idx].has_draft = false;
          if (data.pack) setLetterChainFromPack(data.pack, { fill: true });
          renderPackCards(packId);
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = "Цепочка сброшена к базовым письмам отрасли.";
          }
        } catch (e) {
          if ($("letterLog")) {
            $("letterLog").hidden = false;
            $("letterLog").textContent = String(e);
          }
        }
      });
    }

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

    if ($("localWindowsSave")) {
      $("localWindowsSave").addEventListener("click", async () => {
        try {
          const payload = {
            SCHEDULE_LOCAL_WINDOWS: $("localWindowsEnabled").checked ? "true" : "false",
            SCHEDULE_FOLLOWUPS_FIRST: $("followupsFirst").checked ? "true" : "false",
            SCHEDULE_PREFER_TUE_THU: $("preferTueThu").checked ? "true" : "false",
            SCHEDULE_SKIP_RU_HOLIDAYS: $("skipRuHolidays") && $("skipRuHolidays").checked ? "true" : "false",
            SCHEDULE_SLOTS: ($("localSlots").value || "").trim() || "10:00-11:30,14:30-16:30",
            SCHEDULE_ALLOWED_WEEKDAYS: ($("localAllowedDays").value || "").trim() || "0,1,2,3,4",
            SCHEDULE_PREFERRED_WEEKDAYS: ($("localPreferredDays").value || "").trim() || "1,2,3",
            SCHEDULE_DEFAULT_TIMEZONE: ($("localDefaultTz").value || "").trim() || "Europe/Moscow",
            SCHEDULE_TZ_FAIRNESS: ($("tzFairness") && $("tzFairness").value) || "rotate_daily",
            OOO_PAUSE_DAYS: String(($("oooPauseDays") && $("oooPauseDays").value) || "7"),
          };
          logAction(await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: payload }) }));
          await loadSettingsIntoForms();
          await loadDash();
        } catch (e) {
          logAction(String(e));
        }
      });
    }

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

    if ($("opsNotifySave")) {
      $("opsNotifySave").addEventListener("click", async () => {
        try {
          const payload = opsNotifyPayload();
          const saved = await api("/api/settings", { method: "PUT", body: JSON.stringify({ settings: payload }) });
          let branding = null;
          try {
            branding = await api("/api/ops/telegram/apply-branding", {
              method: "POST",
              body: JSON.stringify({
                bot_token: currentTelegramToken(),
                include_profile_photo: false,
              }),
            });
          } catch (brandErr) {
            branding = { error: String(brandErr) };
          }
          logAction({ settings: saved, branding });
          await loadSettingsIntoForms();
          await loadIntegrationsHealth();
        } catch (e) {
          logAction(String(e));
        }
      });
    }

    if ($("opsTelegramApplyBrand")) {
      $("opsTelegramApplyBrand").addEventListener("click", async () => {
        const log = $("opsTelegramLog");
        try {
          const data = await api("/api/ops/telegram/apply-branding", {
            method: "POST",
            body: JSON.stringify({
              bot_token: currentTelegramToken(),
              include_profile_photo: true,
            }),
          });
          if (log) log.textContent = JSON.stringify(data, null, 2);
        } catch (e) {
          if (log) log.textContent = String(e);
        }
      });
    }

    if ($("opsTelegramVerify")) {
      $("opsTelegramVerify").addEventListener("click", async () => {
        const log = $("opsTelegramLog");
        const info = $("opsTelegramBotInfo");
        try {
          const data = await api("/api/ops/telegram/verify", {
            method: "POST",
            body: JSON.stringify({ bot_token: currentTelegramToken() }),
          });
          if (log) log.textContent = JSON.stringify(data, null, 2);
          if (info) {
            info.classList.remove("hidden");
            const link = data.link
              ? `<a href="${escapeHtml(data.link)}" target="_blank" rel="noopener">@${escapeHtml(data.username || "")}</a>`
              : escapeHtml(data.first_name || "бот");
            info.innerHTML = `Бот: ${link} · id ${escapeHtml(String(data.bot_id || ""))}`;
          }
        } catch (e) {
          if (log) log.textContent = String(e);
          if (info) info.classList.add("hidden");
        }
      });
    }

    if ($("opsTelegramDiscover")) {
      $("opsTelegramDiscover").addEventListener("click", async () => {
        const log = $("opsTelegramLog");
        const selWrap = $("opsNotifyTgChatSelectWrap");
        const sel = $("opsNotifyTgChatSelect");
        try {
          const data = await api("/api/ops/telegram/discover", {
            method: "POST",
            body: JSON.stringify({ bot_token: currentTelegramToken() }),
          });
          if (log) {
            log.textContent = data.hint
              ? `${data.hint}\n\n${JSON.stringify(data, null, 2)}`
              : JSON.stringify(data, null, 2);
          }
          const chats = data.chats || [];
          if (sel && chats.length) {
            sel.innerHTML =
              '<option value="">— выберите чат —</option>' +
              chats
                .map(
                  (c) =>
                    `<option value="${escapeHtml(c.chat_id)}">${escapeHtml(c.title || c.chat_id)} (${escapeHtml(c.type || "")})</option>`
                )
                .join("");
            if (selWrap) selWrap.classList.remove("hidden");
            if (chats.length === 1 && $("opsNotifyTgChat")) {
              $("opsNotifyTgChat").value = chats[0].chat_id;
            }
          } else if (selWrap) {
            selWrap.classList.add("hidden");
          }
        } catch (e) {
          if (log) log.textContent = String(e);
        }
      });
    }

    if ($("opsNotifyTgChatSelect")) {
      $("opsNotifyTgChatSelect").addEventListener("change", () => {
        const v = $("opsNotifyTgChatSelect").value;
        if (v && $("opsNotifyTgChat")) $("opsNotifyTgChat").value = v;
      });
    }

    if ($("opsTelegramTest")) {
      $("opsTelegramTest").addEventListener("click", async () => {
        const log = $("opsTelegramLog");
        try {
          const data = await api("/api/ops/telegram/test", {
            method: "POST",
            body: JSON.stringify({
              bot_token: currentTelegramToken(),
              chat_id: ($("opsNotifyTgChat").value || "").trim(),
            }),
          });
          if (log) log.textContent = JSON.stringify(data, null, 2);
          await loadIntegrationsHealth();
        } catch (e) {
          if (log) log.textContent = String(e);
        }
      });
    }
    if ($("consentReloadBtn")) {
      $("consentReloadBtn").addEventListener("click", () =>
        loadConsentLedger().catch((e) => {
          if ($("consentLog")) $("consentLog").textContent = String(e);
        })
      );
    }
    if ($("consentImportBtn")) {
      $("consentImportBtn").addEventListener("click", async () => {
        try {
          const data = await api("/api/modules/consent/import-suppression", {
            method: "POST",
            body: "{}",
          });
          if ($("consentLog")) $("consentLog").textContent = JSON.stringify(data, null, 2);
          await loadConsentLedger();
        } catch (e) {
          if ($("consentLog")) $("consentLog").textContent = String(e);
        }
      });
    }
    if ($("consentExportBtn")) {
      $("consentExportBtn").addEventListener("click", () => {
        const qs = new URLSearchParams();
        const from = ($("consentFrom") && $("consentFrom").value) || "";
        const to = ($("consentTo") && $("consentTo").value) || "";
        if (from) qs.set("created_from", from + "T00:00:00+00:00");
        if (to) qs.set("created_to", to + "T23:59:59+00:00");
        if ($("consentLegalHold") && $("consentLegalHold").checked) qs.set("legal_hold", "true");
        const path = "/api/modules/consent/export" + (qs.toString() ? "?" + qs.toString() : "");
        downloadApi(path, "quantum-panel-consent-ledger.csv").catch((e) => {
          if ($("consentLog")) $("consentLog").textContent = String(e);
        });
      });
    }
    document.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-company-id]");
      if (!btn || !btn.classList.contains("company-open")) return;
      ev.preventDefault();
      openCompanyCard(btn.getAttribute("data-company-id"));
    });

    if ($("companyPeelClose")) {
      $("companyPeelClose").addEventListener("click", closeCompanyCard);
    }
    if ($("companyPeelBackdrop")) {
      $("companyPeelBackdrop").addEventListener("click", closeCompanyCard);
    }
    if ($("inboxThreadClose")) {
      $("inboxThreadClose").addEventListener("click", closeInboxThread);
    }
    if ($("inboxThreadBackdrop")) {
      $("inboxThreadBackdrop").addEventListener("click", closeInboxThread);
    }
    if ($("inboxReplySend")) {
      $("inboxReplySend").addEventListener("click", () => sendInboxThreadReply().catch(logAction));
    }
    if ($("inboxReplyUseDraft")) {
      $("inboxReplyUseDraft").addEventListener("click", () => {
        if (!activeInboxDraft) return;
        if ($("inboxReplyBody")) $("inboxReplyBody").value = activeInboxDraft;
        if ($("inboxReplyStatus")) {
          $("inboxReplyStatus").textContent =
            "Черновик вставлен — проверьте перед отправкой (APPROVAL_REQUIRED)";
        }
      });
    }
    document.addEventListener("keydown", (ev) => {
      const peel = $("companyPeelAway");
      const thread = $("inboxThreadPeelAway");
      if (ev.key === "Escape" && thread && thread.classList.contains("is-open")) {
        closeInboxThread();
        return;
      }
      if (ev.key === "Escape" && peel && peel.classList.contains("is-open")) closeCompanyCard();
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
        startOpsPolling();
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
        startOpsPolling();
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
