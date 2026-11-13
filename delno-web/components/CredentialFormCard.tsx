"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type CredentialFormField = {
  name: string;
  label: string;
  type: "text" | "password";
  autocomplete?: string;
};

export type CredentialFormSpec = {
  kind: string;
  title: string;
  hint?: string;
  fields: CredentialFormField[];
  submit_label?: string;
  prefill?: Record<string, string>;
  password_required?: boolean;
  login_optional?: boolean;
  require_foreign_consent?: boolean;
  consent_label?: string;
};

type Props = {
  form: CredentialFormSpec;
  busy?: boolean;
  onSubmit: (values: {
    login?: string;
    password?: string;
    foreign_consent?: boolean;
  }) => Promise<void> | void;
  onCancel: () => void;
  className?: string;
};

export function CredentialFormCard({ form, busy, onSubmit, onCancel, className }: Props) {
  const hasLogin = form.fields.some((f) => f.name === "login");
  const [login, setLogin] = useState(form.prefill?.login || "");
  const [password, setPassword] = useState("");
  const [foreignConsent, setForeignConsent] = useState(false);
  const [localError, setLocalError] = useState("");

  async function handleSubmit() {
    setLocalError("");
    const loginOptional = form.login_optional === true || !hasLogin;
    const passwordRequired = form.password_required !== false;
    if (!loginOptional && !login.trim()) {
      setLocalError("Введите логин.");
      return;
    }
    if (passwordRequired && !password.trim()) {
      setLocalError(hasLogin ? "Пароль обязателен." : "Токен обязателен.");
      return;
    }
    if (!login.trim() && !password.trim()) {
      setLocalError("Заполните поля формы.");
      return;
    }
    if (form.require_foreign_consent && !foreignConsent) {
      setLocalError("Нужно согласие на обработку у зарубежного провайдера.");
      return;
    }
    await onSubmit({
      login: login.trim() || undefined,
      password: password.trim() || undefined,
      foreign_consent: form.require_foreign_consent ? foreignConsent : undefined,
    });
  }

  return (
    <div className={cn("hx-confirm hx-secret-form", className)} role="group" aria-label={form.title}>
      <div className="hx-confirm-head">
        <span>{form.title}</span>
        <small>не в чате</small>
      </div>
      {form.hint ? <p className="hx-confirm-summary">{form.hint}</p> : null}
      <div className="hx-secret-fields">
        {form.fields.map((field) => {
          const value = field.name === "password" ? password : login;
          const setValue = field.name === "password" ? setPassword : setLogin;
          return (
            <label key={field.name} className="hx-secret-field">
              <span>{field.label}</span>
              <input
                type={field.type === "password" ? "password" : "text"}
                autoComplete={field.autocomplete || "off"}
                value={value}
                disabled={busy}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void handleSubmit();
                  }
                }}
              />
            </label>
          );
        })}
      </div>
      {form.require_foreign_consent ? (
        <label className="hx-secret-field" style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
          <input
            type="checkbox"
            checked={foreignConsent}
            disabled={busy}
            onChange={(e) => setForeignConsent(e.target.checked)}
            style={{ marginTop: 3 }}
          />
          <span style={{ fontSize: 12, lineHeight: 1.4 }}>
            {form.consent_label ||
              "Согласен на обработку данных у зарубежного облачного провайдера."}
          </span>
        </label>
      ) : null}
      {localError ? <p className="hx-secret-error">{localError}</p> : null}
      <div className="hx-confirm-actions">
        <Button type="button" size="sm" disabled={busy} onClick={() => void handleSubmit()}>
          {busy ? "…" : form.submit_label || "Сохранить"}
        </Button>
        <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </div>
  );
}
