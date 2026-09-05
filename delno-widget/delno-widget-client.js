/**
 * DELNO public widget client (E3.4).
 * Talks to /v1/public/widget/{session,visitor,message} — never to operator/chat.
 */
(function (global) {
  "use strict";

  function cryptoSafeId() {
    try {
      if (global.crypto && global.crypto.randomUUID) return global.crypto.randomUUID();
    } catch (_) {}
    return "w_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10);
  }

  function normalizeApiBase(raw) {
    var base = String(raw || "https://api.dlno.ru/v1/public/widget").replace(/\/$/, "");
    if (base.endsWith("/message")) base = base.slice(0, -8);
    return base;
  }

  function DelnoWidgetClient(options) {
    this.apiBase = normalizeApiBase(options.apiBase);
    this.siteKey = options.siteKey || "demo_dlno";
    this.timeoutMs = options.timeoutMs || 25000;
    this.visitorId =
      options.visitorId ||
      (typeof localStorage !== "undefined" && localStorage.getItem("delno_widget_visitor")) ||
      cryptoSafeId();
    this.sessionId =
      options.sessionId ||
      (typeof localStorage !== "undefined" && localStorage.getItem("delno_widget_session")) ||
      null;

    if (typeof localStorage !== "undefined") {
      localStorage.setItem("delno_widget_visitor", this.visitorId);
      if (this.sessionId) localStorage.setItem("delno_widget_session", this.sessionId);
    }
  }

  DelnoWidgetClient.prototype._fetch = function (path, body) {
    var self = this;
    var ctrl = new AbortController();
    var timer = setTimeout(function () {
      ctrl.abort();
    }, self.timeoutMs);
    return fetch(self.apiBase + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
      body: JSON.stringify(body),
    })
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .finally(function () {
        clearTimeout(timer);
      });
  };

  DelnoWidgetClient.prototype.persistSession = function (id) {
    this.sessionId = id;
    if (typeof localStorage !== "undefined") localStorage.setItem("delno_widget_session", id);
  };

  DelnoWidgetClient.prototype.ensureSession = function () {
    var self = this;
    if (self.sessionId) return Promise.resolve(self.sessionId);
    return self
      ._fetch("/session", {
        site_key: self.siteKey,
        visitor_id: self.visitorId,
        page_url: typeof location !== "undefined" ? location.href : null,
        referrer: typeof document !== "undefined" ? document.referrer || null : null,
        channel: "web",
      })
      .then(function (payload) {
        if (payload.session_id) self.persistSession(payload.session_id);
        return payload;
      });
  };

  DelnoWidgetClient.prototype.syncVisitor = function (fields) {
    var self = this;
    if (!self.sessionId) return Promise.resolve(null);
    return self._fetch("/visitor", {
      site_key: self.siteKey,
      session_id: self.sessionId,
      visitor_id: self.visitorId,
      name: fields.name || null,
      phone: fields.phone || null,
    });
  };

  DelnoWidgetClient.prototype.sendMessage = function (message, visitor, opts) {
    var self = this;
    opts = opts || {};
    var modality = opts.modality || "text";
    var run = function () {
      var body = {
        site_key: self.siteKey,
        session_id: self.sessionId,
        visitor_id: self.visitorId,
        message: message,
        visitor: visitor || {},
        channel: "web",
        input_modality: modality,
      };
      return self._fetch("/message", body).then(function (payload) {
        if (payload.conversation_id) self.persistSession(payload.conversation_id);
        if (payload.lead && payload.lead.id && typeof localStorage !== "undefined") {
          localStorage.setItem("delno_widget_lead_id", payload.lead.id);
        }
        return payload;
      });
    };
    if (!self.sessionId) {
      return self.ensureSession().then(run);
    }
    return run();
  };

  DelnoWidgetClient.prototype.fetchHistory = function () {
    var self = this;
    if (!self.sessionId) return Promise.resolve({ messages: [] });
    return self
      ._fetch("/history", {
        site_key: self.siteKey,
        session_id: self.sessionId,
        visitor_id: self.visitorId,
      })
      .catch(function () {
        return { messages: [] };
      });
  };

  DelnoWidgetClient.prototype.buildTtsUrl = function (text) {
    if (!this.sessionId || !text) return null;
    var params = new URLSearchParams({
      site_key: this.siteKey,
      session_id: this.sessionId,
      visitor_id: this.visitorId,
      text: String(text).slice(0, 800),
    });
    return this.apiBase + "/tts?" + params.toString();
  };

  DelnoWidgetClient.fromParams = function () {
    var params = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
    return new DelnoWidgetClient({
      apiBase: params.get("api") || undefined,
      siteKey: params.get("site_key") || "demo_dlno",
    });
  };

  global.DelnoWidgetClient = DelnoWidgetClient;
})(typeof window !== "undefined" ? window : globalThis);
