/** Canonical V17 marketing site (former `/v2`). */
export const MAIN_LANDING_BASE = "";

export function mainPath(path: string): string {
  if (!path || path === "/") return MAIN_LANDING_BASE || "/";
  return `${MAIN_LANDING_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
