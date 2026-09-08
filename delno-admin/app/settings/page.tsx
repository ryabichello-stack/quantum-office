"use client";

import { useEffect, useState } from "react";
import { AdminShell } from "@/components/AdminShell";
import { useRequirePlatformAdmin } from "@/lib/auth";
import { apiGetPlatformSecrets, apiPatchPlatformSecrets, type SecretGroup } from "@/lib/api";

export default function SettingsPage() {
  const { token, ready } = useRequirePlatformAdmin();
  const [groups, setGroups] = useState<SecretGroup[]>([]);
  const [envPath, setEnvPath] = useState("");
  const [writable, setWritable] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!token) return;
    apiGetPlatformSecrets(token)
      .then((data) => {
        setGroups(data.groups);
        setEnvPath(data.env_file.path);
        setWritable(Boolean(data.env_file.writable));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "load failed"));
  }, [token]);

  function onChange(key: string, value: string) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    const payload = Object.fromEntries(
      Object.entries(draft).filter(([, value]) => value.trim() !== ""),
    );
    if (Object.keys(payload).length === 0) {
      setError("Введите хотя бы одно новое значение");
      return;
    }
    setSaving(true);
    setError("");
    setStatus("");
    try {
      const result = await apiPatchPlatformSecrets(token, payload);
      setStatus(`Сохранено: ${result.changed.join(", ")}`);
      setDraft({});
      const refreshed = await apiGetPlatformSecrets(token);
      setGroups(refreshed.groups);
      setWritable(Boolean(refreshed.env_file.writable));
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
    }
  }

  if (!ready) {
    return (
      <main style={{ maxWidth: 960, margin: "40px auto", padding: 24 }}>
        <p>Загрузка…</p>
      </main>
    );
  }

  return (
    <AdminShell title="Секреты сервера">
      <p style={{ opacity: 0.75, lineHeight: 1.5 }}>
        Ключи сохраняются в <code style={{ color: "#93c5fd" }}>{envPath || "/opt/delno/.env"}</code> на
        сервере. Полные значения после сохранения не показываются — только маска.
      </p>
      {!writable && (
        <p style={{ color: "#fbbf24", marginTop: 12 }}>
          Файл сейчас недоступен для записи из API. Проверьте mount <code>./.env:/opt/delno/.env</code> в
          docker-compose.
        </p>
      )}

      <form onSubmit={onSave} style={{ display: "grid", gap: 28, marginTop: 24 }}>
        {groups.map((group) => (
          <section key={group.id}>
            <h2 style={{ fontSize: 18, marginBottom: 12 }}>{group.title}</h2>
            <div style={{ display: "grid", gap: 16 }}>
              {group.items.map((item) => (
                <label key={item.key} style={{ display: "grid", gap: 6 }}>
                  <span style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                    <strong>{item.label}</strong>
                    <span style={{ fontSize: 12, opacity: 0.7 }}>
                      {item.configured ? `настроено ${item.preview || ""}` : "не задано"}
                    </span>
                  </span>
                  {item.hint && <small style={{ opacity: 0.65 }}>{item.hint}</small>}
                  <input
                    type={item.sensitive ? "password" : "text"}
                    name={item.key}
                    autoComplete="off"
                    placeholder={item.configured ? "Оставьте пустым, чтобы не менять" : "Введите значение"}
                    value={draft[item.key] || ""}
                    onChange={(e) => onChange(item.key, e.target.value)}
                    style={inputStyle}
                    disabled={!writable || saving}
                  />
                  <code style={{ fontSize: 11, opacity: 0.5 }}>{item.key}</code>
                </label>
              ))}
            </div>
          </section>
        ))}

        {error && <p style={{ color: "#f87171" }}>{error}</p>}
        {status && <p style={{ color: "#86efac" }}>{status}</p>}

        <button type="submit" disabled={!writable || saving} style={buttonStyle}>
          {saving ? "Сохраняю…" : "Сохранить на сервер"}
        </button>
      </form>
    </AdminShell>
  );
}

const inputStyle: React.CSSProperties = {
  padding: 12,
  borderRadius: 8,
  border: "1px solid #334155",
  background: "#111827",
  color: "#fff",
};

const buttonStyle: React.CSSProperties = {
  padding: "12px 20px",
  borderRadius: 8,
  border: "none",
  background: "#2563eb",
  color: "#fff",
  cursor: "pointer",
  width: "fit-content",
};
