"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiLogin, apiRegister } from "@/lib/api";
import { LoginConsolePreview } from "@/components/LoginConsolePreview";
import { DelnoMark } from "@/components/DelnoMark";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("owner@delno.one");
  const [password, setPassword] = useState("");
  const [company, setCompany] = useState("");
  const [inn, setInn] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") {
        const { access_token } = await apiLogin(email, password);
        localStorage.setItem("delno_token", access_token);
        router.push("/dashboard");
      } else {
        const result = await apiRegister({
          email,
          password,
          company_name: company,
          inn: inn.replace(/\D/g, "") || undefined,
        });
        localStorage.setItem("delno_token", result.access_token);
        router.push("/dashboard/settings");
      }
    } catch {
      setError(
        mode === "login"
          ? "Неверный email или пароль"
          : "Не удалось создать аккаунт. Email занят или пароль короче 8 символов.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-copy">
        <div className="login-status">
          <i /> {mode === "login" ? "Личный кабинет DELNO" : "Регистрация DELNO"}
        </div>
        <h1>
          {mode === "login" ? (
            <>
              Заявки, диалоги<br />
              <span>и Operator</span>
            </>
          ) : (
            <>
              Запустите<br />
              <span>ИИ-сотрудника</span>
            </>
          )}
        </h1>
        <p>
          {mode === "login"
            ? "Единое рабочее пространство: диалоги, заявки и Operator."
            : "Компания, база знаний и виджет для сайта — за несколько минут."}
        </p>
        <form className="login-form" onSubmit={onSubmit}>
          {mode === "register" && (
            <label>
              Название компании
              <input value={company} onChange={(e) => setCompany(e.target.value)} required minLength={2} />
            </label>
          )}
          <label>
            Email
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === "register" ? 8 : 6}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {mode === "register" && (
            <label>
              ИНН (необязательно)
              <input value={inn} onChange={(e) => setInn(e.target.value)} placeholder="10 или 12 цифр" />
            </label>
          )}
          {error && <p className="form-error">{error}</p>}
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "…" : mode === "login" ? "Войти в кабинет" : "Создать аккаунт"}
          </button>
        </form>
        <p style={{ marginTop: 16, fontSize: 13 }}>
          {mode === "login" ? (
            <>
              Нет аккаунта?{" "}
              <button type="button" className="btn-link" onClick={() => setMode("register")}>
                Зарегистрировать компанию
              </button>
            </>
          ) : (
            <>
              Уже есть аккаунт?{" "}
              <button type="button" className="btn-link" onClick={() => setMode("login")}>
                Войти
              </button>
            </>
          )}
        </p>
        <p style={{ marginTop: 20, fontSize: 11, color: "#888", display: "flex", alignItems: "center", gap: 8 }}>
          <DelnoMark small /> app.dlno.ru
        </p>
      </div>
      <div className="login-preview">
        <LoginConsolePreview />
      </div>
    </main>
  );
}
