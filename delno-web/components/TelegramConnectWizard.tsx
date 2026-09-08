"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Bot, Link2, Unplug } from "lucide-react";
import {
  apiTelegramConnect,
  apiTelegramDisconnect,
  apiTelegramHealth,
  apiTenantChannels,
  type ChannelAccountItem,
} from "@/lib/api";

function statusLabel(status: string) {
  if (status === "active") return "Подключён";
  if (status === "disconnected") return "Отключён";
  return "Ожидает";
}

export function TelegramConnectWizard({ token }: { token: string }) {
  const [accounts, setAccounts] = useState<ChannelAccountItem[]>([]);
  const [botToken, setBotToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [healthNote, setHealthNote] = useState("");

  const active = accounts.find((a) => a.type === "telegram" && a.status === "active");

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const result = await apiTenantChannels(token);
      setAccounts(result.items.filter((item) => item.type === "telegram"));
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
    const value = botToken.trim();
    if (!value) return;
    setBusy(true);
    setError("");
    setStatus("");
    try {
      const result = await apiTelegramConnect(token, value);
      setBotToken("");
      setAccounts((prev) => {
        const rest = prev.filter((item) => item.id !== result.account.id);
        return [result.account, ...rest];
      });
      setStatus(`Бот @${result.account.bot_username || "bot"} подключён — входящие сообщения пойдут в Диалоги.`);
    } catch {
      setError("Не удалось подключить бота. Проверьте токен из BotFather и попробуйте снова.");
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
      const result = await apiTelegramDisconnect(token, active.id);
      setAccounts((prev) => prev.map((item) => (item.id === result.account.id ? result.account : item)));
      setStatus("Telegram-бот отключён.");
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
      const result = await apiTelegramHealth(token, active.id);
      if (result.ok) {
        setHealthNote("Webhook и бот в порядке.");
      } else {
        setHealthNote("Проблема с webhook или токеном — попробуйте переподключить.");
      }
    } catch {
      setHealthNote("Проверка не удалась.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="settings-section panel-card">
      <h2>
        <Bot size={18} style={{ verticalAlign: "middle", marginRight: 8 }} />
        Telegram-бот (Branded)
      </h2>
      <p className="muted tight">
        Подключите своего бота из BotFather — DELNO будет отвечать клиентам от его имени. Сообщения появятся в
        разделе «Диалоги».
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
            <li>Откройте @BotFather в Telegram и создайте бота (/newbot).</li>
            <li>Скопируйте HTTP API token и вставьте ниже.</li>
            <li>DELNO сам настроит webhook — ничего вручную в Telegram не нужно.</li>
          </ol>
          <label style={{ display: "grid", gap: 6, fontSize: 12, fontWeight: 700 }}>
            Bot token
            <input
              type="password"
              value={botToken}
              onChange={(e) => setBotToken(e.target.value)}
              placeholder="123456789:AAH…"
              autoComplete="off"
              style={{ padding: "11px 13px", borderRadius: 10, border: "1px solid var(--line)" }}
            />
          </label>
          <button type="submit" className="btn-primary" style={{ width: "fit-content" }} disabled={busy || !botToken.trim()}>
            {busy ? "Подключаю…" : "Подключить бота"}
          </button>
        </form>
      )}

      {status && <p className="status-ok">{status}</p>}
      {error && <p className="status-error">{error}</p>}
    </section>
  );
}
