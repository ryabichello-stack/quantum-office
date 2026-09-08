const API_URL = process.env.NEXT_PUBLIC_DELNO_API_URL || "http://127.0.0.1:18020";

export async function apiLogin(email: string, password: string) {
  const res = await fetch(`${API_URL}/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Login failed");
  return res.json() as Promise<{ access_token: string }>;
}

export async function apiGetTenants(token: string) {
  const res = await fetch(`${API_URL}/v1/admin/tenants`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load tenants");
  return res.json();
}

export async function apiGetCmsPages(token: string) {
  const res = await fetch(`${API_URL}/v1/admin/cms/pages`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load CMS pages");
  return res.json();
}

export { API_URL };
