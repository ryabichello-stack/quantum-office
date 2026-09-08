"use client";

type ConfirmCardProps = {
  summary: string;
  toolName: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmCard({ summary, toolName, busy, onConfirm, onCancel }: ConfirmCardProps) {
  return (
    <div className="operator-confirm">
      <div className="result-head">
        <span>DELNO хочет изменить</span>
        <small>{toolName}</small>
      </div>
      <p style={{ margin: "0 0 12px" }}>{summary}</p>
      <div className="operator-confirm-actions">
        <button type="button" className="btn-primary" disabled={busy} onClick={onConfirm}>
          {busy ? "…" : "Применить"}
        </button>
        <button type="button" className="btn-ghost" disabled={busy} onClick={onCancel}>
          Отмена
        </button>
      </div>
    </div>
  );
}
