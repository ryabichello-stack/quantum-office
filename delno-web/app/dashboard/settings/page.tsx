"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import {
  apiFeatureFlags,
  apiPartySuggest,
  apiPatchFeatureFlag,
  apiTenantLegalGet,
  apiTenantLegalPut,
  type FeatureFlag,
  type LegalProfile,
  type PartySuggestion,
} from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";

export default function SettingsPage() {
  const { token } = useRequireAuth();
  const [legal, setLegal] = useState<LegalProfile | null>(null);
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [innQuery, setInnQuery] = useState("");
  const [suggestions, setSuggestions] = useState<PartySuggestion[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!token) return;
    apiTenantLegalGet(token)
      .then((r) => setLegal(r.legal))
      .catch(() => undefined);
    apiFeatureFlags(token)
      .then(setFlags)
      .catch(() => undefined);
  }, [token]);

  useEffect(() => {
    if (!token || innQuery.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => {
      apiPartySuggest(token, innQuery.trim())
        .then((r) => setSuggestions(r.suggestions || []))
        .catch(() => setSuggestions([]));
    }, 300);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [token, innQuery]);

  async function saveInn(inn: string) {
    if (!token) return;
    setError("");
    setStatus("");
    try {
      const result = await apiTenantLegalPut(token, inn);
      setLegal(result.legal);
      setInnQuery(result.legal.company_name || inn);
      setSuggestions([]);
      setStatus("Юридический профиль обновлён");
    } catch {
      setError("Не удалось сохранить профиль по ИНН");
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const digits = innQuery.replace(/\D/g, "");
    if (digits.length === 10 || digits.length === 12) {
      await saveInn(digits);
    } else {
      setError("Укажите корректный ИНН (10 или 12 цифр) или выберите из списка");
    }
  }

  async function toggleFlag(flag: FeatureFlag) {
    if (!token) return;
    const updated = await apiPatchFeatureFlag(token, flag.flag_key, !flag.enabled);
    setFlags((prev) => prev.map((f) => (f.flag_key === updated.flag_key ? updated : f)));
  }

  return (
    <DashboardFrame>
      <div className="page-head">
        <small>Настройки tenant</small>
        <h1>Настройки</h1>
        <p>Юридический профиль и feature flags</p>
      </div>

      <section className="settings-section panel-card">
        <h2>Юридический профиль (ИНН)</h2>
        {legal?.company_name && (
          <div className="legal-box">
            <div style={{ fontWeight: 700 }}>{legal.company_name}</div>
            {legal.inn && <div style={{ fontSize: 12, color: "#888" }}>ИНН {legal.inn}</div>}
            {legal.address && <div style={{ fontSize: 13, marginTop: 6 }}>{legal.address}</div>}
            {legal.okved && <div style={{ fontSize: 12, color: "#888" }}>ОКВЭД {legal.okved}</div>}
          </div>
        )}
        <form onSubmit={onSubmit} style={{ display: "grid", gap: 12, maxWidth: 480 }}>
          <label style={{ display: "grid", gap: 6, fontSize: 12, fontWeight: 700 }}>
            Компания или ИНН
            <input
              value={innQuery}
              onChange={(e) => setInnQuery(e.target.value)}
              placeholder="Название или ИНН"
              style={{ padding: "11px 13px", borderRadius: 10, border: "1px solid var(--line)" }}
            />
          </label>
          {suggestions.length > 0 && (
            <ul className="suggest-list">
              {suggestions.map((s) => (
                <li key={`${s.inn}-${s.company_name}`}>
                  <button type="button" onClick={() => s.inn && saveInn(s.inn)}>
                    <div style={{ fontWeight: 600 }}>{s.company_name || s.value}</div>
                    {s.inn && <div style={{ fontSize: 11, color: "#888" }}>ИНН {s.inn}</div>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button type="submit" className="btn-primary" style={{ width: "fit-content" }}>
            Сохранить по ИНН
          </button>
        </form>
        {status && <p className="status-ok">{status}</p>}
        {error && <p className="status-error">{error}</p>}
      </section>

      <section className="settings-section panel-card">
        <h2>Feature flags</h2>
        {flags.length === 0 && <p className="inbox-empty">Нет флагов или нет доступа</p>}
        {flags.map((flag) => (
          <div key={flag.flag_key} className="flag-row">
            <span>{flag.flag_key}</span>
            <button type="button" className="btn-ghost" onClick={() => toggleFlag(flag)}>
              {flag.enabled ? "Вкл" : "Выкл"}
            </button>
          </div>
        ))}
      </section>
    </DashboardFrame>
  );
}
