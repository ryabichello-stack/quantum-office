"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  apiGetAnalyticsPages,
  apiGetAnalyticsRecent,
  apiGetAnalyticsReferrers,
  apiGetAnalyticsSummary,
  apiGetAnalyticsTimeseries,
  type AnalyticsPages,
  type AnalyticsRecent,
  type AnalyticsReferrers,
  type AnalyticsSummary,
  type AnalyticsTimeseries,
} from "@/lib/api";

const RANGES = [
  { label: "7 дней", days: 7 },
  { label: "30 дней", days: 30 },
  { label: "90 дней", days: 90 },
];

function StatCard({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div
      style={{
        background: "#111827",
        border: "1px solid #1f2937",
        borderRadius: 12,
        padding: "16px 18px",
        minWidth: 0,
      }}
    >
      <div style={{ fontSize: 12, opacity: 0.65, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 650, letterSpacing: "-0.02em" }}>{value}</div>
      {hint ? <div style={{ fontSize: 12, opacity: 0.5, marginTop: 6 }}>{hint}</div> : null}
    </div>
  );
}

function MiniBars({ points }: { points: AnalyticsTimeseries["points"] }) {
  const max = Math.max(1, ...points.map((p) => p.sessions));
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 120, marginTop: 12 }}>
      {points.map((p) => (
        <div
          key={p.date}
          title={`${p.date}: ${p.sessions} сессий, ${p.pageviews} просмотров`}
          style={{
            flex: 1,
            minWidth: 4,
            height: `${Math.max(4, Math.round((p.sessions / max) * 100))}%`,
            background: "linear-gradient(180deg, #3b82f6, #1d4ed8)",
            borderRadius: 3,
            opacity: 0.9,
          }}
        />
      ))}
    </div>
  );
}

export default function AnalyticsPage() {
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [series, setSeries] = useState<AnalyticsTimeseries["points"]>([]);
  const [pages, setPages] = useState<AnalyticsPages["pages"]>([]);
  const [referrers, setReferrers] = useState<AnalyticsReferrers["referrers"]>([]);
  const [recent, setRecent] = useState<AnalyticsRecent["hits"]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const token = localStorage.getItem("delno_token");
    if (!token) {
      window.location.href = "/login";
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [s, t, p, r, h] = await Promise.all([
        apiGetAnalyticsSummary(token, days),
        apiGetAnalyticsTimeseries(token, days),
        apiGetAnalyticsPages(token, days),
        apiGetAnalyticsReferrers(token, days),
        apiGetAnalyticsRecent(token),
      ]);
      setSummary(s);
      setSeries(t.points);
      setPages(p.pages);
      setReferrers(r.referrers);
      setRecent(h.hits);
    } catch {
      setError("Не удалось загрузить статистику. Проверьте вход (platform admin).");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const maxPageviews = useMemo(
    () => Math.max(1, ...pages.map((p) => p.pageviews)),
    [pages],
  );

  return (
    <main style={{ maxWidth: 1100, margin: "32px auto", padding: "0 20px 48px" }}>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 28 }}>Статистика сайта</h1>
          <p style={{ margin: "8px 0 0", opacity: 0.65 }}>
            Своя аналитика dlno.ru — без Яндекс.Метрики. Визиты, отказы, страницы.
          </p>
        </div>
        <nav style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Link href="/tenants" style={{ color: "#93c5fd" }}>
            Tenants
          </Link>
          <button
            type="button"
            onClick={() => void load()}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #334155",
              background: "#111827",
              color: "#e8eef5",
              cursor: "pointer",
            }}
          >
            Обновить
          </button>
        </nav>
      </header>

      <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
        {RANGES.map((r) => (
          <button
            key={r.days}
            type="button"
            onClick={() => setDays(r.days)}
            style={{
              padding: "8px 12px",
              borderRadius: 999,
              border: days === r.days ? "1px solid #3b82f6" : "1px solid #334155",
              background: days === r.days ? "#1e3a8a" : "#0f172a",
              color: "#e8eef5",
              cursor: "pointer",
            }}
          >
            {r.label}
          </button>
        ))}
      </div>

      {error ? <p style={{ color: "#f87171", marginTop: 16 }}>{error}</p> : null}
      {loading && !summary ? <p style={{ opacity: 0.6, marginTop: 24 }}>Загрузка…</p> : null}

      {summary ? (
        <>
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: 12,
              marginTop: 24,
            }}
          >
            <StatCard label="Сессии" value={summary.sessions} hint={`за ${summary.days} дн.`} />
            <StatCard label="Просмотры" value={summary.pageviews} />
            <StatCard label="Отказы" value={`${summary.bounce_rate}%`} hint="1 страница без взаимодействия" />
            <StatCard label="Стр. / сессия" value={summary.pages_per_session} />
            <StatCard label="Сегодня" value={summary.sessions_today} hint={`${summary.pageviews_today} просм.`} />
            <StatCard label="Вчера" value={summary.sessions_yesterday} />
          </section>

          <section
            style={{
              marginTop: 28,
              background: "#111827",
              border: "1px solid #1f2937",
              borderRadius: 12,
              padding: 18,
            }}
          >
            <h2 style={{ margin: 0, fontSize: 16 }}>Сессии по дням</h2>
            {series.length === 0 ? (
              <p style={{ opacity: 0.55, marginTop: 12 }}>Пока нет данных — откройте dlno.ru пару раз.</p>
            ) : (
              <MiniBars points={series} />
            )}
          </section>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
              gap: 16,
              marginTop: 20,
            }}
          >
            <section style={panelStyle}>
              <h2 style={h2Style}>Топ страниц</h2>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th align="left">Путь</th>
                    <th align="right">Просм.</th>
                    <th align="right">Сессии</th>
                  </tr>
                </thead>
                <tbody>
                  {pages.map((p) => (
                    <tr key={p.path}>
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          <span>{p.path}</span>
                          <span
                            style={{
                              display: "block",
                              height: 3,
                              borderRadius: 2,
                              background: "#2563eb",
                              width: `${Math.round((p.pageviews / maxPageviews) * 100)}%`,
                              opacity: 0.7,
                            }}
                          />
                        </div>
                      </td>
                      <td align="right">{p.pageviews}</td>
                      <td align="right">{p.sessions}</td>
                    </tr>
                  ))}
                  {pages.length === 0 ? (
                    <tr>
                      <td colSpan={3} style={{ opacity: 0.5 }}>
                        Нет данных
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </section>

            <section style={panelStyle}>
              <h2 style={h2Style}>Источники</h2>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th align="left">Источник</th>
                    <th align="right">Сессии</th>
                  </tr>
                </thead>
                <tbody>
                  {referrers.map((r) => (
                    <tr key={r.source}>
                      <td>{r.source}</td>
                      <td align="right">{r.sessions}</td>
                    </tr>
                  ))}
                  {referrers.length === 0 ? (
                    <tr>
                      <td colSpan={2} style={{ opacity: 0.5 }}>
                        Нет данных
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </section>
          </div>

          <section style={{ ...panelStyle, marginTop: 20 }}>
            <h2 style={h2Style}>Последние просмотры</h2>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th align="left">Время</th>
                  <th align="left">Путь</th>
                  <th align="left">Источник</th>
                  <th align="left">Сессия</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((h) => (
                  <tr key={h.id}>
                    <td style={{ whiteSpace: "nowrap", opacity: 0.75 }}>
                      {h.created_at ? new Date(h.created_at).toLocaleString("ru-RU") : "—"}
                    </td>
                    <td>{h.path}</td>
                    <td style={{ opacity: 0.8 }}>{h.utm_source || h.referrer || "direct"}</td>
                    <td style={{ fontFamily: "ui-monospace, monospace", opacity: 0.6 }}>{h.session_id}</td>
                  </tr>
                ))}
                {recent.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ opacity: 0.5 }}>
                      Пока пусто
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </main>
  );
}

const panelStyle: CSSProperties = {
  background: "#111827",
  border: "1px solid #1f2937",
  borderRadius: 12,
  padding: 18,
};

const h2Style: CSSProperties = { margin: "0 0 12px", fontSize: 16 };

const tableStyle: CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 14,
};
