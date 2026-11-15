"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  apiConnectCatalog,
  apiConnectSubmit,
  apiGoogleCalendarStart,
  type ConnectProvider,
  type ConnectionStatus,
} from "@/lib/api";

const KINDS = [
  { id: "calendar" as const, title: "Календарь" },
  { id: "mail" as const, title: "Почта" },
  { id: "conference" as const, title: "Видеовстречи" },
];

export function OfficeConnect({ token }: { token: string }) {
  const [kind, setKind] = useState<(typeof KINDS)[number]["id"]>("calendar");
  const [providers, setProviders] = useState<ConnectProvider[]>([]);
  const [providerId, setProviderId] = useState("");
  const [connection, setConnection] = useState<ConnectionStatus | null>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [calendarUrl, setCalendarUrl] = useState("");
  const [consent, setConsent] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const provider = providers.find((item) => item.id === providerId) || null;

  useEffect(() => {
    let cancelled = false;
    apiConnectCatalog(token, kind)
      .then((res) => {
        if (cancelled) return;
        setProviders(res.providers || []);
        setProviderId(res.connection?.provider || res.providers?.[0]?.id || "");
        setConnection(res.connection || null);
        setLogin("");
        setPassword("");
        setCalendarUrl("");
        setConsent(false);
        setMessage(res.connection?.message_ru || "");
        setError("");
      })
      .catch(() => {
        if (!cancelled) setError("Не удалось загрузить провайдеров");
      });
    return () => {
      cancelled = true;
    };
  }, [token, kind]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!provider) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await apiConnectSubmit(token, kind, {
        provider: provider.id,
        login: login.trim() || undefined,
        password: password || undefined,
        calendar_url: calendarUrl.trim() || undefined,
        foreign_consent: consent,
      });
      setPassword("");
      setConnection(result.connection || null);
      if (result.ok) setMessage(result.message_ru || "Подключено");
      else setError(result.message_ru || "Проверка не прошла");
    } catch {
      setPassword("");
      setError("Не удалось отправить форму");
    } finally {
      setBusy(false);
    }
  }

  async function startGoogle() {
    setBusy(true);
    setError("");
    try {
      const started = await apiGoogleCalendarStart(token);
      if (started.authorize_url) {
        window.location.href = started.authorize_url;
        return;
      }
      setError(started.message_ru || "Кнопка Google недоступна");
    } catch {
      setError("Кнопка Google недоступна");
    } finally {
      setBusy(false);
    }
  }

  const status = connection?.status || "disconnected";

  return (
    <div className="office-connect">
      <div className="hx-flag-list">
        {KINDS.map((item) => (
          <button
            key={item.id}
            type="button"
            className="hx-chip-link"
            aria-pressed={kind === item.id}
            onClick={() => setKind(item.id)}
          >
            {item.title}
          </button>
        ))}
      </div>
      <p className={status === "connected" ? "hx-inline-ok" : "hx-muted"}>
        Статус: {status === "connected" ? "подключено" : status === "failed" ? "ошибка проверки" : "не подключено"}
        {connection?.message_ru ? ` — ${connection.message_ru}` : ""}
      </p>
      <label>
        Провайдер
        <select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
          {providers.map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </select>
      </label>
      {provider ? <p className="hx-muted">{provider.hint}</p> : null}
      {provider?.auth === "oauth" ? (
        <button type="button" className="hx-primary-btn" disabled={busy} onClick={() => void startGoogle()}>
          Войти через Google
        </button>
      ) : null}
      <form className="hx-form" onSubmit={onSubmit}>
        {provider && provider.auth !== "internal" ? (
          <>
            <label>
              Логин
              <input
                value={login}
                autoComplete="off"
                placeholder={provider.example_login || "ivan@example.ru"}
                onChange={(e) => setLogin(e.target.value)}
              />
            </label>
            <label>
              {provider.password_label || "Пароль приложения"}
              <input
                type="password"
                value={password}
                autoComplete="new-password"
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
          </>
        ) : null}
        {provider?.needs_calendar_url ? (
          <label>
            Ссылка CalDAV
            <input
              value={calendarUrl}
              placeholder="https://caldav.example.ru/calendars/ivan/"
              onChange={(e) => setCalendarUrl(e.target.value)}
            />
          </label>
        ) : null}
        {provider?.foreign ? (
          <label>
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> Согласен на
            обработку у провайдера вне РФ
          </label>
        ) : null}
        <button type="submit" className="hx-primary-btn" disabled={busy || !provider}>
          Проверить и подключить
        </button>
      </form>
      {message ? <p className="hx-inline-ok">{message}</p> : null}
      {error ? <p className="hx-inline-error">{error}</p> : null}
    </div>
  );
}