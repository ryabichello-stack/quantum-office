"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Shared page chrome for every cabinet screen — same language as Hermes.
 */
export function CabinetPage({
  kicker = "DELNO",
  title,
  lead,
  actions,
  children,
  className,
  wide,
}: {
  kicker?: string;
  title: string;
  lead?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  wide?: boolean;
}) {
  return (
    <div className={cn("hx-app hx-page", className)}>
      <header className="hx-topbar hx-page-top">
        <div className="hx-brand">
          <div>
            <small>{kicker}</small>
            <strong>{title}</strong>
            {lead ? <p className="hx-page-lead">{lead}</p> : null}
          </div>
        </div>
        {actions ? <div className="hx-top-actions">{actions}</div> : null}
      </header>
      <div className={cn("hx-page-body", wide && "is-wide")}>{children}</div>
    </div>
  );
}

export function CabinetCard({
  title,
  hint,
  children,
  className,
}: {
  title?: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("hx-card", className)}>
      {(title || hint) && (
        <div className="hx-card-head">
          {title ? <h2>{title}</h2> : null}
          {hint ? <p>{hint}</p> : null}
        </div>
      )}
      {children}
    </section>
  );
}

export function CabinetEmpty({
  title,
  lead,
  action,
}: {
  title: string;
  lead?: string;
  action?: ReactNode;
}) {
  return (
    <div className="hx-empty hx-empty-panel">
      <p className="hx-empty-kicker">пока пусто</p>
      <h2 className="hx-empty-title">{title}</h2>
      {lead ? <p className="hx-empty-lead">{lead}</p> : null}
      {action}
    </div>
  );
}
