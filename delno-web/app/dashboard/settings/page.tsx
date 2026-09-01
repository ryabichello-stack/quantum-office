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
import { buttonPrimary, buttonGhost, card, colors, input } from "@/lib/ui";

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
    <>
      <h1 style={{ margin: "0 0 8px", fontSize: 28 }}>Настройки</h1>
      <p style={{ margin: "0 0 24px", color: colors.muted }}>Юридический профиль и feature flags tenant</p>

      <section style={{ ...card, marginBottom: 20 }}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Юридический профиль (ИНН)</h2>
        {legal?.company_name && (
          <div style={{ marginBottom: 16, padding: 12, background: "#f8fafc", borderRadius: 8 }}>
            <div style={{ fontWeight: 700 }}>{legal.company_name}</div>
            {legal.inn && <div style={{ fontSize: 13, color: colors.muted }}>ИНН {legal.inn}</div>}
            {legal.address && <div style={{ fontSize: 13, marginTop: 4 }}>{legal.address}</div>}
            {legal.okved && <div style={{ fontSize: 13, color: colors.muted }}>ОКВЭД {legal.okved}</div>}
          </div>
        )}
        <form onSubmit={onSubmit} style={{ display: "grid", gap: 10, maxWidth: 480 }}>
          <label style={{ display: "grid", gap: 6, fontSize: 13 }}>
            Компания или ИНН
            <input
              style={input}
              value={innQuery}
              onChange={(e) => setInnQuery(e.target.value)}
              placeholder="Название или ИНН"
            />
          </label>
          {suggestions.length > 0 && (
            <ul style={{ listStyle: "none", margin: 0, padding: 0, border: `1px solid ${colors.border}`, borderRadius: 8 }}>
              {suggestions.map((s) => (
                <li key={`${s.inn}-${s.company_name}`}>
                  <button
                    type="button"
                    onClick={() => s.inn && saveInn(s.inn)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: 10,
                      border: "none",
                      background: "#fff",
                      cursor: "pointer",
                      borderBottom: `1px solid ${colors.border}`,
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{s.company_name || s.value}</div>
                    {s.inn && <div style={{ fontSize: 12, color: colors.muted }}>ИНН {s.inn}</div>}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <button type="submit" style={buttonPrimary}>
              Сохранить по ИНН
            </button>
          </div>
        </form>
        {status && <p style={{ color: colors.success }}>{status}</p>}
        {error && <p style={{ color: colors.danger }}>{error}</p>}
      </section>

      <section style={card}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Feature flags</h2>
        {flags.length === 0 && <p style={{ color: colors.muted }}>Нет флагов или нет доступа</p>}
        <div style={{ display: "grid", gap: 8 }}>
          {flags.map((flag) => (
            <label
              key={flag.flag_key}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px 0",
                borderBottom: `1px solid ${colors.border}`,
              }}
            >
              <span>{flag.flag_key}</span>
              <button type="button" style={buttonGhost} onClick={() => toggleFlag(flag)}>
                {flag.enabled ? "Вкл" : "Выкл"}
              </button>
            </label>
          ))}
        </div>
      </section>
    </>
  );
}
