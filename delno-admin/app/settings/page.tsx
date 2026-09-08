"use client";

import { useEffect, useState } from "react";
import { AdminFrame } from "@/components/AdminFrame";
import { useRequirePlatformAdmin } from "@/lib/auth";
import { apiGetPlatformSecrets, apiPatchPlatformSecrets, type SecretGroup } from "@/lib/api";

export default function SettingsPage() {
  const { token } = useRequirePlatformAdmin();
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
    const payload = Object.fromEntries(Object.entries(draft).filter(([, value]) => value.trim() !== ""));
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

  return (
    <AdminFrame>
      <div className="page-head">
        <small>Platform</small>
        <h1>Секреты сервера</h1>
        <p>
          Ключи пишутся в <code>{envPath || "/opt/delno/.env"}</code>. После сохранения полные значения не
          показываются.
        </p>
      </div>

      {!writable && (
        <p className="status-error" style={{ marginBottom: 16 }}>
          Файл недоступен для записи из API. Проверьте mount <code>./.env:/opt/delno/.env</code> в docker-compose.
        </p>
      )}

      <form className="login-form" onSubmit={onSave} style={{ maxWidth: 560 }}>
        {groups.map((group) => (
          <section key={group.id} className="settings-section panel-card">
            <h2>{group.title}</h2>
            {group.items.map((item) => (
              <label key={item.key} style={{ marginBottom: 14 }}>
                <span style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <span>{item.label}</span>
                  <small style={{ color: "#888" }}>
                    {item.configured ? `настроено ${item.preview || ""}` : "не задано"}
                  </small>
                </span>
                {item.hint && (
                  <small style={{ display: "block", color: "#888", fontWeight: 400, marginBottom: 4 }}>
                    {item.hint}
                  </small>
                )}
                <input
                  type={item.sensitive ? "password" : "text"}
                  name={item.key}
                  autoComplete="off"
                  placeholder={item.configured ? "Пусто = не менять" : "Введите значение"}
                  value={draft[item.key] || ""}
                  onChange={(e) => onChange(item.key, e.target.value)}
                  disabled={!writable || saving}
                />
                <code style={{ fontSize: 10, color: "#aaa" }}>{item.key}</code>
              </label>
            ))}
          </section>
        ))}

        {error && <p className="form-error">{error}</p>}
        {status && <p className="status-ok">{status}</p>}

        <button type="submit" className="btn-primary" disabled={!writable || saving}>
          {saving ? "Сохраняю…" : "Сохранить на сервер"}
        </button>
      </form>
    </AdminFrame>
  );
}
