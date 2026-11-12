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
};

type Props = {
  form: CredentialFormSpec;
  busy?: boolean;
  onSubmit: (values: { login?: string; password?: string }) => Promise<void> | void;
  onCancel: () => void;
  className?: string;
};

export function CredentialFormCard({ form, busy, onSubmit, onCancel, className }: Props) {
  const [login, setLogin] = useState(form.prefill?.login || "");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState("");

  async function handleSubmit() {
    setLocalError("");
    if (!login.trim() && !password.trim()) {
      setLocalError("Введите логин и пароль.");
      return;
    }
    if (!password.trim()) {
      setLocalError("SIP-пароль обязателен.");
      return;
    }
    await onSubmit({ login: login.trim() || undefined, password: password.trim() });
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
