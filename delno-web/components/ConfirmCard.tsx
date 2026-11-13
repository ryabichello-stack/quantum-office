"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ConfirmCardProps = {
  summary: string;
  toolName: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  className?: string;
};

export function ConfirmCard({
  summary,
  toolName,
  busy,
  onConfirm,
  onCancel,
  className,
}: ConfirmCardProps) {
  return (
    <div className={cn("hx-confirm", className)} role="group" aria-label="Подтверждение действия">
      <div className="hx-confirm-head">
        <span>Нужно подтверждение</span>
        <small>{toolName}</small>
      </div>
      <p className="hx-confirm-summary">{summary}</p>
      <div className="hx-confirm-actions">
        <Button type="button" size="sm" disabled={busy} onClick={onConfirm}>
          {busy ? "…" : "Применить"}
        </Button>
        <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </div>
  );
}
