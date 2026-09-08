"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AdminLoginPreview } from "@/components/AdminLoginPreview";
import { ADMIN_TOKEN_KEY, apiLogin, apiMe } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const reason = new URLSearchParams(window.location.search).get("reason");
    if (reason === "session_expired") {
      setError("Сессия истекла или был изменён JWT Secret. Войдите снова — после входа всё заработает.");
    }
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { access_token } = await apiLogin(email.trim(), password);
      const me = await apiMe(access_token);
      if (me.role !== "platform_admin") {
        setError("Нужен аккаунт platform_admin");
        return;
      }
      localStorage.setItem(ADMIN_TOKEN_KEY, access_token);
      router.push("/settings");
    } catch {
      setError("Неверный email или пароль");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-copy">
        <div className="login-status">
          <i /> Platform admin · admin.dlno.ru
        </div>
        <h1>
          Клиенты,
          <br />
          <span>CMS и секреты</span>
        </h1>
        <p>Управление платформой DELNO: tenants, CMS и ключи сервера без SSH.</p>
        <form className="login-form" onSubmit={onSubmit}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@dlno.ru"
              autoComplete="username"
              required
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Вход…" : "Войти"}
          </button>
        </form>
      </div>
      <div className="login-preview">
        <AdminLoginPreview />
      </div>
    </main>
  );
}
