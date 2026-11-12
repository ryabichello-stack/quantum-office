"use client";

import { useEffect, useState } from "react";
import { DashboardFrame } from "@/components/DashboardFrame";
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
      const r = await apiBillingEnsure(token);
      setSummary(r);
    } catch {
      setError("Не удалось выдать стартовый баланс");
    } finally {
      setBusy(false);
    }
  }

  const llm = summary?.llm;

  return (
    <DashboardFrame>
      <main className="cabinet-main">
        <div className="page-head">
          <small>Биллинг</small>
          <h1>Затраты</h1>
          <p>Токены и деньги по клиенту</p>
        </div>

        <section className="settings-section panel-card">
          <h2>Этот кабинет</h2>
          <p className="muted tight">
            Токены LLM, себестоимость OpenAI (USD) и начисление клиенту (RUB).
          </p>
          {error ? <p className="status-error">{error}</p> : null}
          {summary ? (
            <>
              <div className="billing-kpis">
                <div>
                  <strong>{fmtTokens(llm?.tokens_total)}</strong>
                  <span>токенов всего</span>
                  <small>
                    in {fmtTokens(llm?.prompt_tokens)} · out {fmtTokens(llm?.completion_tokens)} ·{" "}
                    {llm?.events ?? 0} ходов
                  </small>
                </div>
                <div>
                  <strong>{fmtUsd(llm?.cost_vendor_usd)}</strong>
                  <span>себестоимость</span>
                  <small>vendor USD · OpenAI list</small>
                </div>
                <div>
                  <strong>{fmtRub(llm?.cost_client_rub, summary.balance.currency)}</strong>
                  <span>клиенту</span>
                  <small>
                    баланс {fmtRub(summary.balance.token_credits, summary.balance.currency)}
                  </small>
                </div>
              </div>
              <p>{summary.message_ru}</p>
              <button
                type="button"
                className="btn-primary"
                style={{ width: "fit-content" }}
                disabled={busy}
                onClick={() => void ensureCredits()}
              >
                {busy ? "…" : "Выдать стартовый баланс"}
              </button>
            </>
          ) : (
            <p>Загружаю…</p>
          )}
        </section>

        {isPlatform && overview ? (
          <section className="settings-section panel-card">
            <h2>Все клиенты</h2>
            <p className="muted tight">{overview.message_ru}</p>
            <div className="billing-kpis">
              <div>
                <strong>{fmtTokens(overview.totals.tokens_total)}</strong>
                <span>токенов платформы</span>
              </div>
              <div>
                <strong>{fmtUsd(overview.totals.cost_vendor_usd)}</strong>
                <span>себестоимость всего</span>
              </div>
              <div>
                <strong>{fmtRub(overview.totals.cost_client_rub)}</strong>
                <span>начислено клиентам</span>
              </div>
            </div>
            <div className="table-wrap">
              <table className="billing-table">
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
                        <small>{t.tenant_slug}</small>
                      </td>
                      <td>
                        {fmtTokens(t.llm.tokens_total)}
                        <small>
                          in {fmtTokens(t.llm.prompt_tokens)} / out {fmtTokens(t.llm.completion_tokens)}
                        </small>
                      </td>
                      <td>{fmtUsd(t.llm.cost_vendor_usd)}</td>
                      <td>{fmtRub(t.llm.cost_client_rub)}</td>
                      <td>
                        {fmtRub(t.balance.token_credits, t.balance.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : null}
      </main>
    </DashboardFrame>
  );
}
