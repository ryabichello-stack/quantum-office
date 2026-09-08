"use client";

import { useCallback, useEffect, useState } from "react";
import { AdminFrame } from "@/components/AdminFrame";
import { useRequirePlatformAdmin } from "@/lib/auth";
import {
  apiGetPlatformSecrets,
  apiPatchPlatformSecrets,
  apiRefreshPlatformOptions,
  apiTestOpenAiKey,
  type OpenAiOptions,
  type SecretGroup,
  type SecretItem,
} from "@/lib/api";

function formatFetchError(code: string | null | undefined): string {
  if (!code) return "";
  if (code === "auth_failed") {
    return "OpenAI отклонил ключ (401). Проверьте, что вставлен ключ sk-... с platform.openai.com, а не пароль от админки.";
  }
  if (code === "openai_key_missing") {
    return "Сначала сохраните OpenAI API Key.";
  }
  if (code === "openai_key_invalid_format") {
    return "Ключ OpenAI должен начинаться с sk- (скопируйте с platform.openai.com/account/api-keys).";
  }
  return code;
}

function optionsForItem(item: SecretItem, options: OpenAiOptions | null): string[] {
  if (!options) return item.value ? [item.value] : [];
  if (item.options_key === "chat_models") return options.chat_models;
  if (item.options_key === "realtime_models") return options.realtime_models;
  if (item.options_key === "realtime_voices") return options.realtime_voices;
  return [];
}

export default function SettingsPage() {
  const { token } = useRequirePlatformAdmin();
  const [groups, setGroups] = useState<SecretGroup[]>([]);
  const [options, setOptions] = useState<OpenAiOptions | null>(null);
  const [envPath, setEnvPath] = useState("");
  const [writable, setWritable] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [selectValues, setSelectValues] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [testingKey, setTestingKey] = useState(false);

  const applyPayload = useCallback((data: Awaited<ReturnType<typeof apiGetPlatformSecrets>>) => {
    setGroups(data.groups);
    setOptions(data.options);
    setEnvPath(data.env_file.path);
    setWritable(Boolean(data.env_file.writable));
    const selects: Record<string, string> = {};
    for (const group of data.groups) {
      for (const item of group.items) {
        if (item.control === "select") {
          selects[item.key] = item.value || item.preview || "";
        }
      }
    }
    setSelectValues(selects);
  }, []);

  useEffect(() => {
    if (!token) return;
    apiGetPlatformSecrets(token)
      .then(async (data) => {
        applyPayload(data);
        const openaiKeySet = data.groups
          .flatMap((g) => g.items)
          .some((item) => item.key === "OPENAI_API_KEY" && item.configured);
        const needsLiveLists =
          openaiKeySet &&
          (data.options.source !== "openai" ||
            data.options.realtime_models.length <= 2 ||
            data.options.chat_models.length <= 2);
        if (needsLiveLists) {
          setRefreshing(true);
          try {
            const refreshed = await apiRefreshPlatformOptions(token);
            setOptions(refreshed);
            if (refreshed.source === "openai") {
              setStatus(
                `Списки моделей загружены из OpenAI (${refreshed.realtime_models.length} realtime, ${refreshed.chat_models.length} chat)`,
              );
            }
          } catch {
            /* keep fallback lists from initial load */
          } finally {
            setRefreshing(false);
          }
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : "load failed"));
  }, [token, applyPayload]);

  function onChange(key: string, value: string) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function onSelectChange(key: string, value: string) {
    setSelectValues((prev) => ({ ...prev, [key]: value }));
  }

  async function refreshOptions() {
    if (!token) return;
    setRefreshing(true);
    setError("");
    try {
      const refreshed = await apiRefreshPlatformOptions(token);
      setOptions(refreshed);
      setStatus(
        refreshed.source === "openai"
          ? `Списки обновлены из OpenAI (${refreshed.realtime_models.length} realtime, ${refreshed.chat_models.length} chat)`
          : "OpenAI недоступен — показаны резервные списки",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  async function testOpenAiKey(configured: boolean) {
    if (!token) return;
    const draftKey = draft["OPENAI_API_KEY"]?.trim() || "";
    if (draftKey && !draftKey.startsWith("sk-")) {
      setError(formatFetchError("openai_key_invalid_format"));
      setStatus("");
      return;
    }
    if (!draftKey && !configured) {
      setError("Введите ключ sk-... в поле или сначала сохраните его на сервер");
      setStatus("");
      return;
    }

    setTestingKey(true);
    setError("");
    setStatus("");
    try {
      const result = await apiTestOpenAiKey(token, draftKey || undefined);
      if (result.ok) {
        setStatus(
          `Ключ работает (${result.key_preview}): ${result.realtime_models_count} realtime, ${result.chat_models_count} chat моделей в OpenAI`,
        );
      } else {
        setError(formatFetchError(result.error));
      }
    } catch (err) {
      setError(formatFetchError(err instanceof Error ? err.message : "test failed"));
    } finally {
      setTestingKey(false);
    }
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;

    const payload: Record<string, string> = {};
    for (const [key, value] of Object.entries(selectValues)) {
      if (value.trim()) payload[key] = value.trim();
    }
    for (const [key, value] of Object.entries(draft)) {
      if (value.trim()) payload[key] = value.trim();
    }

    const draftOpenAi = draft["OPENAI_API_KEY"]?.trim();
    if (draftOpenAi && !draftOpenAi.startsWith("sk-")) {
      setError(formatFetchError("openai_key_invalid_format"));
      return;
    }

    if (Object.keys(payload).length === 0) {
      setError("Нечего сохранять — выберите модель/голос или введите ключ");
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
      applyPayload(refreshed);
      if (result.changed.includes("OPENAI_API_KEY")) {
        try {
          const live = await apiRefreshPlatformOptions(token);
          setOptions(live);
          setStatus(
            live.source === "openai"
              ? `Ключ сохранён. Списки моделей загружены (${live.realtime_models.length} realtime). Выберите модель и голос.`
              : live.fetch_error === "auth_failed"
                ? "Ключ сохранён, но OpenAI его не принял — проверьте sk-... ключ, не пароль от входа."
                : `Ключ сохранён, но OpenAI не ответил${live.fetch_error ? `: ${formatFetchError(live.fetch_error)}` : ""}`,
          );
        } catch {
          /* initial payload already applied */
        }
      }
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
          Ключи и модели пишутся в <code>{envPath || "/opt/delno/secrets/platform.env"}</code>. Перед сохранением можно
          проверить ключ кнопкой «Тест ключа».
        </p>
      </div>

        {!writable && (
        <p className="status-error" style={{ marginBottom: 16 }}>
          Файл недоступен для записи из API. Проверьте mount <code>./secrets:/opt/delno/secrets</code> в docker-compose.
        </p>
      )}

      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <button type="button" className="btn-ghost" disabled={refreshing || !token} onClick={() => void refreshOptions()}>
          {refreshing ? "Обновляю…" : "Обновить списки из OpenAI"}
        </button>
        {options && (
          <small style={{ alignSelf: "center", color: options.fetch_error ? "#c44" : "#888" }}>
            источник: {options.source === "openai" ? "OpenAI API" : "резервный список"}
            {options.fetch_error ? ` — ${formatFetchError(options.fetch_error)}` : ""}
          </small>
        )}
      </div>

      <form className="login-form" onSubmit={onSave} style={{ maxWidth: 560 }}>
        {groups.map((group) => (
          <section key={group.id} className="settings-section panel-card">
            <h2>{group.title}</h2>
            {group.items.map((item) => {
              const selectOptions = optionsForItem(item, options);
              const currentSelect = selectValues[item.key] || item.value || "";
              return (
                <label key={item.key} style={{ marginBottom: 14, display: "grid", gap: 6 }}>
                  <span style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                    <span>{item.label}</span>
                    <small style={{ color: "#888" }}>
                      {item.control === "select"
                        ? currentSelect || "не выбрано"
                        : item.configured
                          ? `настроено ${item.preview || ""}`
                          : "не задано"}
                    </small>
                  </span>
                  {item.hint && (
                    <small style={{ display: "block", color: "#888", fontWeight: 400 }}>
                      {item.hint}
                    </small>
                  )}
                  {item.control === "select" ? (
                    <select
                      name={item.key}
                      value={currentSelect}
                      onChange={(e) => onSelectChange(item.key, e.target.value)}
                      disabled={!writable || saving}
                      style={{ padding: "12px 14px", borderRadius: 10, border: "1px solid var(--line)" }}
                    >
                      <option value="">— выберите —</option>
                      {selectOptions.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                      {currentSelect && !selectOptions.includes(currentSelect) && (
                        <option value={currentSelect}>{currentSelect} (текущее)</option>
                      )}
                    </select>
                  ) : item.key === "OPENAI_API_KEY" ? (
                    <div style={{ display: "flex", gap: 8, alignItems: "stretch" }}>
                      <input
                        type="password"
                        name={item.key}
                        autoComplete="off"
                        placeholder={
                          item.configured ? "Пусто = не менять (sk-...)" : "sk-proj-... с platform.openai.com"
                        }
                        value={draft[item.key] || ""}
                        onChange={(e) => onChange(item.key, e.target.value)}
                        disabled={!writable || saving}
                        style={{ flex: 1, minWidth: 0 }}
                      />
                      <button
                        type="button"
                        className="btn-ghost"
                        disabled={!token || testingKey || saving}
                        onClick={() => void testOpenAiKey(item.configured)}
                        style={{ whiteSpace: "nowrap", alignSelf: "stretch" }}
                      >
                        {testingKey ? "Проверяю…" : "Тест ключа"}
                      </button>
                    </div>
                  ) : (
                    <input
                      type={item.control === "password" || item.sensitive ? "password" : "text"}
                      name={item.key}
                      autoComplete="off"
                      placeholder={
                        item.configured ? "Пусто = не менять" : "Введите значение"
                      }
                      value={draft[item.key] || ""}
                      onChange={(e) => onChange(item.key, e.target.value)}
                      disabled={!writable || saving}
                    />
                  )}
                  <code style={{ fontSize: 10, color: "#aaa" }}>{item.key}</code>
                </label>
              );
            })}
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
