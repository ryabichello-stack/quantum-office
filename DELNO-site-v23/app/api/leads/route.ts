export const runtime = "nodejs";

type LeadPayload = {
  source?: unknown;
  name?: unknown;
  phone?: unknown;
  email?: unknown;
  company?: unknown;
  website?: unknown;
  inn?: unknown;
};

const clean = (value: unknown, max = 200) =>
  typeof value === "string" ? value.trim().slice(0, max) : "";

export async function POST(request: Request) {
  const apiBase = (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "")
    .replace(/\/$/, "");
  const tenantSlug = process.env.DELNO_TENANT_SLUG || "delno-demo";

  let input: LeadPayload;
  try {
    input = (await request.json()) as LeadPayload;
  } catch {
    return Response.json({ error: "INVALID_JSON" }, { status: 400 });
  }

  const lead = {
    source: clean(input.source, 120),
    name: clean(input.name, 120),
    phone: clean(input.phone, 60),
    email: clean(input.email, 160),
    company: clean(input.company, 160),
    website: clean(input.website, 255),
    inn: clean(input.inn, 14).replace(/\D/g, "").slice(0, 12) || undefined,
  };

  if (!lead.name || !lead.phone) {
    return Response.json({ error: "NAME_AND_PHONE_REQUIRED" }, { status: 400 });
  }

  if (lead.phone.replace(/\D/g, "").length < 10) {
    return Response.json({ error: "PHONE_INVALID" }, { status: 400 });
  }

  if (apiBase) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`${apiBase}/v1/public/leads`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-Slug": tenantSlug,
        },
        body: JSON.stringify({
          ...lead,
          source: lead.source || "Сайт DELNO",
        }),
        signal: controller.signal,
      });
      clearTimeout(timeout);

      if (response.ok) {
        const data = (await response.json().catch(() => ({}))) as { lead_id?: string };
        return Response.json({ ok: true, lead_id: data.lead_id ?? null });
      }

      const detail = await response.text().catch(() => "");
      if (response.status === 404) {
        return Response.json({ error: "TENANT_NOT_FOUND", detail: detail.slice(0, 500) }, { status: 502 });
      }
      if (response.status === 422 || response.status === 400) {
        return Response.json({ error: "VALIDATION_FAILED", detail: detail.slice(0, 500) }, { status: 400 });
      }
      return Response.json(
        { error: "DELNO_API_LEAD_FAILED", detail: detail.slice(0, 500) },
        { status: 502 },
      );
    } catch (err) {
      clearTimeout(timeout);
      const message = err instanceof Error ? err.message : "network_error";
      return Response.json({ error: "DELNO_API_UNREACHABLE", detail: message }, { status: 502 });
    }
  }

  const webhook = process.env.LEAD_WEBHOOK_URL;
  const telegramToken = process.env.TELEGRAM_BOT_TOKEN;
  const telegramChatId = process.env.TELEGRAM_CHAT_ID;
  if (!webhook && (!telegramToken || !telegramChatId)) {
    return Response.json({ error: "LEAD_STORAGE_NOT_CONFIGURED" }, { status: 503 });
  }

  const payload = { ...lead, created_at: new Date().toISOString() };
  const telegramText = [
    "Новая заявка DELNO",
    `Источник: ${lead.source || "Сайт"}`,
    `Имя: ${lead.name}`,
    `Телефон: ${lead.phone}`,
    lead.company ? `Компания: ${lead.company}` : "",
    lead.email ? `Почта: ${lead.email}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  const response = webhook
    ? await fetch(webhook, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
    : await fetch(`https://api.telegram.org/bot${telegramToken}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: telegramChatId, text: telegramText }),
      });

  if (!response.ok) {
    return Response.json({ error: "LEAD_DELIVERY_FAILED" }, { status: 502 });
  }
  return Response.json({ ok: true });
}
