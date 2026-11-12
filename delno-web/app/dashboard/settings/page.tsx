"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import {
  apiFeatureFlags,
  apiPartySuggest,
  apiPatchFeatureFlag,
  apiTenantLegalGet,
  apiTenantLegalPut,
  apiTenantWidget,
  type FeatureFlag,
  type LegalProfile,
  type PartySuggestion,
} from "@/lib/api";
import { DashboardFrame } from "@/components/DashboardFrame";
import { CabinetCard, CabinetPage } from "@/components/CabinetPage";
import { TelegramConnectWizard } from "@/components/TelegramConnectWizard";
import { MaxConnectWizard } from "@/components/MaxConnectWizard";

export default function SettingsPage() {
  const { token } = useRequireAuth();
  const [legal, setLegal] = useState<LegalProfile | null>(null);
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [innQuery, setInnQuery] = useState("");
  const [suggestions, setSuggestions] = useState<PartySuggestion[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [widgetEmbed, setWidgetEmbed] = useState("");
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!token) return;
    apiTenantLegalGet(token)
      .then((r) => setLegal(r.legal))
      .catch(() => undefined);
    apiFeatureFlags(token)
      .then(setFlags)
      .catch(() => undefined);
    apiTenantWidget(token)
      .then((r) => setWidgetEmbed(r.embed_html))
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
      <CabinetPage
        kicker="Кабинет"
        title="Настройки"
        lead="Профиль компании, каналы и виджет. Базу знаний лучше вести в разделе «Знания» или через Hermes."
        actions={
          <Link href="/dashboard/hermes" className="hx-chip-link">
            Настроить голосом в Hermes
          </Link>
        }
      >
        <CabinetCard title="Компания" hint="ИНН и юридический профиль">
          {legal?.company_name ? (
            <div className="hx-legal-box">
              <strong>{legal.company_name}</strong>
              {legal.inn ? <small>ИНН {legal.inn}</small> : null}
              {legal.address ? <p>{legal.address}</p> : null}
            </div>
          ) : null}
          <form className="hx-form" onSubmit={onSubmit}>
            <label>
              Компания или ИНН
              <input
                value={innQuery}
                onChange={(e) => setInnQuery(e.target.value)}
                placeholder="Название или ИНН"
              />
            </label>
            {suggestions.length > 0 ? (
              <ul className="hx-suggest">
                {suggestions.map((s) => (
                  <li key={`${s.inn}-${s.company_name}`}>
                    <button type="button" onClick={() => s.inn && void saveInn(s.inn)}>
                      <strong>{s.company_name || s.value}</strong>
                      {s.inn ? <small>ИНН {s.inn}</small> : null}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            <button type="submit" className="hx-primary-btn">
              Сохранить
            </button>
          </form>
          {status ? <p className="hx-inline-ok">{status}</p> : null}
          {error ? <p className="hx-inline-error">{error}</p> : null}
        </CabinetCard>

        <CabinetCard title="Виджет на сайт" hint="Вставьте код — посетители смогут писать вам">
          {widgetEmbed ? <pre className="hx-embed">{widgetEmbed}</pre> : <p className="hx-muted">Загрузка…</p>}
        </CabinetCard>

        {token ? (
          <CabinetCard title="Каналы" hint="Telegram и MAX">
            <div className="hx-wizards">
              <TelegramConnectWizard token={token} />
              <MaxConnectWizard token={token} />
            </div>
          </CabinetCard>
        ) : null}

        <CabinetCard title="Флаги" hint="Технические переключатели">
          {flags.length === 0 ? <p className="hx-muted">Нет флагов или нет доступа</p> : null}
          <div className="hx-flag-list">
            {flags.map((flag) => (
              <div key={flag.flag_key} className="hx-flag-row">
                <span>{flag.flag_key}</span>
                <button type="button" className="hx-chip-link" onClick={() => void toggleFlag(flag)}>
                  {flag.enabled ? "Вкл" : "Выкл"}
                </button>
              </div>
            ))}
          </div>
        </CabinetCard>
      </CabinetPage>
    </DashboardFrame>
  );
}
