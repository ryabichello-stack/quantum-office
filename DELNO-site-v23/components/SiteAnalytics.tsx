"use client";

import { useEffect, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";

const SITE_KEY = process.env.NEXT_PUBLIC_ANALYTICS_SITE_KEY || "dlno.ru";
const SESSION_KEY = "delno_sid";

function getSessionId(): string {
  try {
    const existing = sessionStorage.getItem(SESSION_KEY);
    if (existing && existing.length >= 8) return existing;
    const id =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID().replace(/-/g, "")
        : `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
    sessionStorage.setItem(SESSION_KEY, id);
    return id;
  } catch {
    return `s${Date.now().toString(36)}`;
  }
}

function utmFromSearch(search: string): {
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
} {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const pick = (k: string) => {
    const v = params.get(k);
    return v ? v.slice(0, 120) : undefined;
  };
  return {
    utm_source: pick("utm_source"),
    utm_medium: pick("utm_medium"),
    utm_campaign: pick("utm_campaign"),
  };
}

function sendHit(payload: Record<string, unknown>, useBeacon = false) {
  const body = JSON.stringify(payload);
  const url = "/api/analytics/hit";
  if (useBeacon && typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
    try {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(url, blob)) return;
    } catch {
      /* fall through */
    }
  }
  void fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => undefined);
}

/**
 * First-party pageview tracker → delno-api (independent of Yandex Metrika).
 */
export function SiteAnalytics() {
  const pathname = usePathname() || "/";
  const searchParams = useSearchParams();
  const startedAt = useRef<number>(Date.now());
  const engaged = useRef(false);
  const lastPath = useRef<string>("");

  useEffect(() => {
    const search = searchParams?.toString() ? `?${searchParams.toString()}` : "";
    const path = pathname || "/";
    if (path === lastPath.current) return;
    lastPath.current = path;
    startedAt.current = Date.now();
    engaged.current = false;

    const session_id = getSessionId();
    const utm = utmFromSearch(search);
    sendHit({
      site_key: SITE_KEY,
      session_id,
      path,
      referrer: typeof document !== "undefined" ? document.referrer || undefined : undefined,
      title: typeof document !== "undefined" ? document.title.slice(0, 255) : undefined,
      event: "pageview",
      ...utm,
    });

    const onEngage = () => {
      if (engaged.current) return;
      engaged.current = true;
      sendHit({
        site_key: SITE_KEY,
        session_id,
        path,
        event: "engage",
        engaged: true,
      });
    };

    const events: Array<keyof WindowEventMap> = ["scroll", "click", "keydown", "touchstart"];
    events.forEach((ev) => window.addEventListener(ev, onEngage, { once: true, passive: true }));

    const onLeave = () => {
      sendHit(
        {
          site_key: SITE_KEY,
          session_id,
          path,
          event: "leave",
          duration_ms: Date.now() - startedAt.current,
          engaged: engaged.current,
        },
        true,
      );
    };
    window.addEventListener("pagehide", onLeave);

    return () => {
      events.forEach((ev) => window.removeEventListener(ev, onEngage));
      window.removeEventListener("pagehide", onLeave);
      onLeave();
    };
  }, [pathname, searchParams]);

  return null;
}
