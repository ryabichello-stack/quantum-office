"use client";

import { useState } from "react";
import { Check, Sparkles } from "lucide-react";
import {
  apiOnboardingPublish,
  apiOnboardingResolveConflict,
  apiOnboardingSummary,
  type OnboardingSummary,
} from "@/lib/api";

const MISSING_LABELS: Record<string, string> = {
  company_name: "название",
  services: "услуги",
  prices: "цены",
  address: "адрес",
  hours: "график",
  contacts: "контакты",
};

export function OnboardingSummaryCard({
  token,
  published,
  onPublished,
  onRefresh,
}: {
  token: string;
  published: boolean;
  onPublished: () => void;
  onRefresh: () => void;
}) {
  const [summary, setSummary] = useState<OnboardingSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(false);

  async function loadSummary() {
    setLoading(true);
    setError("");
    try {
      const data = await apiOnboardingSummary(token);
      setSummary(data);
      setExpanded(true);
    } catch {
      setError("Не удалось загрузить сводку.");
    } finally {
      setLoading(false);
    }
  }

  async function onPublish() {
    if (!summary || publishing) return;
    setPublishing(true);
    setError("");
    try {
      const result = await apiOnboardingPublish(token);
      if (!result.ok) {
        setError(result.error === "unresolved_conflicts" ? "Сначала уточните расходящиеся цены." : "Не удалось опубликовать.");
        return;
      }
      onPublished();
      onRefresh();
    } catch {
      setError("Не удалось опубликовать знания.");
    } finally {
      setPublishing(false);
    }
  }

  async function onResolveConflict(field: string, price: number) {
    setError("");
    try {
      await apiOnboardingResolveConflict(token, field, price);
      await loadSummary();
      onRefresh();
    } catch {
      setError("Не удалось сохранить выбор.");
    }
  }

  if (published) return null;

  return (
    <div className="onboarding-summary-wrap">
      {!expanded ? (
        <button type="button" className="btn-ghost onboarding-summary-toggle" onClick={() => void loadSummary()} disabled={loading}>
          {loading ? "…" : "Показать сводку DELNO"}
        </button>
      ) : summary ? (
        <div className="delno-result onboarding-summary-card">
          <div className="result-head">
            <span>
              <Sparkles /> Вот что DELNO понял
            </span>
          </div>

          <div className="onboarding-summary-grid">
            {summary.profile.company_name && (
              <div>
                <small>Компания</small>
                <p>{summary.profile.company_name}</p>
              </div>
            )}
            {summary.profile.services && summary.profile.services.length > 0 && (
              <div>
                <small>Услуги</small>
                <ul>
                  {summary.profile.services.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {summary.profile.prices && summary.profile.prices.length > 0 && (
              <div>
                <small>Основные цены</small>
                <ul>
                  {summary.profile.prices.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            )}
            {summary.profile.address && (
              <div>
                <small>Адрес</small>
                <p>{summary.profile.address}</p>
              </div>
            )}
            {summary.profile.hours && (
              <div>
                <small>График</small>
                <p>{summary.profile.hours}</p>
              </div>
            )}
            {summary.profile.contacts && (
              <div>
                <small>Контакты</small>
                <p>{summary.profile.contacts}</p>
              </div>
            )}
          </div>

          {summary.missing_fields.length > 0 && (
            <p className="onboarding-summary-missing">
              Не хватает: {summary.missing_fields.map((m) => MISSING_LABELS[m] || m).join(", ")}
            </p>
          )}

          {summary.conflicts.length > 0 && (
            <div className="onboarding-conflicts">
              <p style={{ margin: "0 0 8px", fontWeight: 700 }}>Уточните цены:</p>
              {summary.conflicts.map((conflict) => (
                <div key={conflict.field} className="onboarding-conflict-row">
                  <span>{conflict.label}</span>
                  <div className="onboarding-conflict-actions">
                    {conflict.values.map((v) => (
                      <button
                        key={`${conflict.field}-${v.price}-${v.source_label}`}
                        type="button"
                        className="btn-ghost"
                        onClick={() => void onResolveConflict(conflict.field, v.price)}
                      >
                        {v.source_label}: {v.price} ₽
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {error && <p className="status-error">{error}</p>}

          <div className="onboarding-summary-actions">
            <button
              type="button"
              className="btn-primary"
              disabled={publishing || summary.conflicts.length > 0 || !summary.document_ids.length}
              onClick={() => void onPublish()}
            >
              <Check size={16} style={{ verticalAlign: -3, marginRight: 6 }} />
              {publishing ? "…" : "Подтвердить и опубликовать"}
            </button>
            <button type="button" className="btn-ghost" onClick={() => void loadSummary()} disabled={loading}>
              Обновить
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
