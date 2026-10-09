/** Public site origin (prod: https://dlno.ru). */
export function getSiteUrl(): string {
  const raw = process.env.NEXT_PUBLIC_SITE_URL?.trim() || "https://dlno.ru";
  return raw.replace(/\/$/, "");
}
