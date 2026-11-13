"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DashboardFrame } from "@/components/DashboardFrame";
import { CabinetCard, CabinetPage } from "@/components/CabinetPage";
import { useRequireAuth } from "@/lib/auth";
import {
  apiAdminBillingOverview,
  apiBillingEnsure,
  apiBillingSummary,
  type BillingSummary,
  type PlatformBillingOverview,
} from "@/lib/hermesApi";

function fmtTokens(n: number | undefined) {
  return (n ?? 0).toLocaleString("ru-RU");
}

function fmtUsd(n: number | undefined) {
  return `$${(n ?? 0).toFixed(4)}`;
}

function fmtRub(n: number | undefined, currency = "RUB") {
  return `${(n ?? 0).toFixed(2)} ${currency}`;
}

export default function BillingPage() {
  const { token, me } = useRequireAuth();
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [overview, setOverview] = useState<PlatformBillingOverview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isPlatform = me?.role === "platform_admin";

  useEffect(() => {
    if (!token) return;
    setError("");
    apiBillingSummary(token)
      .then(setSummary)
      .catch(() => setError("Не удалось загрузить затраты"));
    if (isPlatform) {
      apiAdminBillingOverview(token)
        .then(setOverview)
        .catch(() => undefined);
    }
  }, [token, isPlatform]);

  async function ensureCredits() {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      setSummary(await apiBillingEnsure(token));
    } catch {
      setError("Не удалось выдать стартовый баланс");
    } finally {
      setBusy(false);
    }
  }

  const llm = summary?.llm;

  return (
    <DashboardFrame>
      <CabinetPage
        kicker="Деньги"
        title="Затраты"
        lead="Токены, себестоимость и сколько начислено этому кабинету."
        actions={
          <Link href="/dashboard/hermes" className="hx-chip-link">
            Спросить Hermes
          </Link>
        }
      >
        <div className="hx-kpi-row">
          <div className="hx-kpi">
            <strong>{fmtTokens(llm?.tokens_total)}</strong>
            <span>токенов</span>
            <small>
              in {fmtTokens(llm?.prompt_tokens)} · out {fmtTokens(llm?.completion_tokens)}
            </small>
          </div>
          <div className="hx-kpi">
            <strong>{fmtUsd(llm?.cost_vendor_usd)}</strong>
            <span>себестоимость</span>
            <small>OpenAI USD</small>
          </div>
          <div className="hx-kpi">
            <strong>{fmtRub(llm?.cost_client_rub, summary?.balance.currency)}</strong>
            <span>клиенту</span>
            <small>
              баланс {fmtRub(summary?.balance.token_credits, summary?.balance.currency)}
            </small>
          </div>
        </div>

        <CabinetCard title="Этот кабинет" hint={summary?.message_ru || "Сводка по LLM"}>
          {error ? <p className="hx-inline-error">{error}</p> : null}
          <button type="button" className="hx-primary-btn" disabled={busy} onClick={() => void ensureCredits()}>
            {busy ? "…" : "Выдать стартовый баланс"}
          </button>
        </CabinetCard>

        {isPlatform && overview ? (
          <CabinetCard title="Все клиенты" hint={overview.message_ru}>
            <div className="hx-kpi-row compact">
              <div className="hx-kpi">
                <strong>{fmtTokens(overview.totals.tokens_total)}</strong>
                <span>токенов платформы</span>
              </div>
              <div className="hx-kpi">
                <strong>{fmtUsd(overview.totals.cost_vendor_usd)}</strong>
                <span>себестоимость</span>
              </div>
              <div className="hx-kpi">
                <strong>{fmtRub(overview.totals.cost_client_rub)}</strong>
                <span>начислено</span>
              </div>
            </div>
            <div className="hx-table-wrap">
              <table className="hx-table">
                <thead>
                  <tr>
                    <th>Клиент</th>
                    <th>Токены</th>
                    <th>Себест. USD</th>
                    <th>Клиенту RUB</th>
                    <th>Баланс</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.tenants.map((t) => (
                    <tr key={t.tenant_id}>
                      <td>
                        <strong>{t.tenant_name || t.tenant_slug}</strong>
                        <small className="hx-td-sub">{t.tenant_slug}</small>
                      </td>
                      <td>{fmtTokens(t.llm.tokens_total)}</td>
                      <td>{fmtUsd(t.llm.cost_vendor_usd)}</td>
                      <td>{fmtRub(t.llm.cost_client_rub)}</td>
                      <td>{fmtRub(t.balance.token_credits, t.balance.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CabinetCard>
        ) : null}
      </CabinetPage>
    </DashboardFrame>
  );
}
