"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link2, MessageCircle, Unplug } from "lucide-react";
import {
  apiMaxConnect,
  apiMaxDisconnect,
  apiMaxHealth,
  apiTenantChannels,
  type ChannelAccountItem,
} from "@/lib/api";

function statusLabel(status: string) {
  if (status === "active") return "Подключён";
  if (status === "disconnected") return "Отключён";
  return "Ожидает";
}

export function MaxConnectWizard({ token }: { token: string }) {
  const [accounts, setAccounts] = useState<ChannelAccountItem[]>([]);
  const [accessToken, setAccessToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [healthNote, setHealthNote] = useState("");

  const active = accounts.find((a) => a.type === "max" && a.status === "active");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiTenantChannels(token);
      setAccounts(result.items.filter((item) => item.type === "max"));
    } catch {
      setError("Не удалось загрузить каналы");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function onConnect(e: FormEvent) {
    e.preventDefault();
    const value = accessToken.trim();
    if (!value) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const result = await apiMaxConnect(token, value);
      setAccessToken("");
      setAccounts((prev) => {
        const rest = prev.filter((item) => item.id !== result.account.id);
        return [result.account, ...rest];
      });
      const label = result.account.bot_username ? `@${result.account.bot_username}` : result.account.bot_name || "бот";
      setStatus(`${label} подключён — входящие сообщения пойдут в Диалоги.`);
    } catch {
      setError("Не удалось подключить MAX-бота. Проверьте access token из MAX для бизнеса.");
    } finally {
      setBusy(false);
    }
  }

  async function onDisconnect() {
    if (!active) return;
    setBusy(true);
    setError("");
    setStatus("");
    setHealthNote("");
    try {
      const result = await apiMaxDisconnect(token, active.id);
      setAccounts((prev) => prev.map((item) => (item.id === result.account.id ? result.account : item)));
      setStatus("MAX-бот отключён.");
    } catch {
      setError("Не удалось отключить бота.");
    } finally {
      setBusy(false);
    }
  }

  async function onHealthcheck() {
    if (!active) return;
    setBusy(true);
    setHealthNote("");
    try {
      const result = await apiMaxHealth(token, active.id);
      setHealthNote(result.ok ? "Webhook и бот в порядке." : "Проблема с webhook или токеном — попробуйте переподключить.");
    } catch {
      setHealthNote("Проверка не удалась.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="settings-section panel-card">
      <h2>
        <MessageCircle size={18} style={{ verticalAlign: "middle", marginRight: 8 }} />
        MAX-бот (Branded)
      </h2>
      <p className="muted tight">
        Подключите своего бота из MAX для бизнеса — DELNO будет отвечать клиентам в мессенджере MAX. Бот остаётся вашим,
        мы только настраиваем webhook и обработку сообщений.
      </p>

      {loading ? (
        <p className="inbox-empty">Загрузка…</p>
      ) : active ? (
        <div className="telegram-connected">
          <div className="telegram-connected-head">
            <span className="onboarding-badge status-published">{statusLabel(active.status)}</span>
            {active.bot_username && <strong>@{active.bot_username}</strong>}
            {active.bot_name && <span className="muted tight">{active.bot_name}</span>}
          </div>
          {active.webhook_url && (
            <div className="embed-code-wrap">
              <small>Webhook (настраивается автоматически)</small>
              <pre className="embed-code">{active.webhook_url}</pre>
            </div>
          )}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button type="button" className="btn-ghost" disabled={busy} onClick={() => void onHealthcheck()}>
              <Link2 size={16} /> Проверить
            </button>
            <button type="button" className="btn-ghost" disabled={busy} onClick={() => void onDisconnect()}>
              <Unplug size={16} /> Отключить
            </button>
          </div>
          {healthNote && <p className="status-ok">{healthNote}</p>}
        </div>
      ) : (
        <form onSubmit={onConnect} style={{ display: "grid", gap: 12, maxWidth: 520 }}>
          <ol className="muted tight" style={{ margin: 0, paddingLeft: 18 }}>
            <li>Создайте и верифицируйте бота в MAX для бизнеса (бот принадлежит вам).</li>
            <li>Скопируйте access token из настроек бота.</li>
            <li>DELNO зарегистрирует webhook на platform-api2.max.ru — вручную ничего настраивать не нужно.</li>
          </ol>
          <label style={{ display: "grid", gap: 6, fontSize: 12, fontWeight: 700 }}>
            Access token
            <input
              type="password"
              value={accessToken}
              onChange={(e) => setAccessToken(e.target.value)}
              placeholder="Токен из MAX для бизнеса"
              autoComplete="off"
              style={{ padding: "11px 13px", borderRadius: 10, border: "1px solid var(--line)" }}
            />
          </label>
          <button type="submit" className="btn-primary" style={{ width: "fit-content" }} disabled={busy || !accessToken.trim()}>
            {busy ? "Подключаю…" : "Подключить MAX-бота"}
          </button>
        </form>
      )}

      {status && <p className="status-ok">{status}</p>}
      {error && <p className="status-error">{error}</p>}
    </section>
  );
}
