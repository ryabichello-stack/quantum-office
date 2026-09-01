"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { apiLogin } from "@/lib/api";
import { LoginConsolePreview } from "@/components/LoginConsolePreview";
import { DelnoMark } from "@/components/DelnoMark";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("owner@delno.one");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const { access_token } = await apiLogin(email, password);
      localStorage.setItem("delno_token", access_token);
      router.push("/dashboard");
    } catch {
      setError("Неверный email или пароль");
    }
  }

  return (
    <main className="login-page">
      <div className="login-copy">
        <div className="login-status">
          <i /> Личный кабинет DELNO
        </div>
        <h1>
          Заявки, диалоги<br />
          <span>и Operator</span>
        </h1>
        <p>Единое рабочее пространство — как на главной странице сайта: диалоги слева, контекст и итоги справа.</p>
        <form className="login-form" onSubmit={onSubmit}>
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
              autoComplete="current-password"
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <button type="submit" className="btn-primary">
            Войти в кабинет
          </button>
        </form>
        <p style={{ marginTop: 20, fontSize: 11, color: "#888", display: "flex", alignItems: "center", gap: 8 }}>
          <DelnoMark small /> delno-demo · staging
        </p>
      </div>
      <div className="login-preview">
        <LoginConsolePreview />
      </div>
    </main>
  );
}
