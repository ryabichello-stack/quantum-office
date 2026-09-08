export const colors = {
  bg: "#f4f6f8",
  surface: "#ffffff",
  border: "#e2e8f0",
  text: "#0f172a",
  muted: "#64748b",
  accent: "#111827",
  accentSoft: "#eef2ff",
  danger: "#dc2626",
  success: "#15803d",
};

export const card: React.CSSProperties = {
  background: colors.surface,
  border: `1px solid ${colors.border}`,
  borderRadius: 12,
  padding: 20,
};

export const buttonPrimary: React.CSSProperties = {
  padding: "10px 16px",
  borderRadius: 8,
  border: "none",
  background: colors.accent,
  color: "#fff",
  cursor: "pointer",
  fontWeight: 600,
};

export const buttonGhost: React.CSSProperties = {
  padding: "10px 16px",
  borderRadius: 8,
  border: `1px solid ${colors.border}`,
  background: "#fff",
  color: colors.text,
  cursor: "pointer",
};

export const input: React.CSSProperties = {
  padding: "10px 12px",
  borderRadius: 8,
  border: `1px solid ${colors.border}`,
  width: "100%",
  boxSizing: "border-box",
};

export const table: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 14,
};

export const th: React.CSSProperties = {
  textAlign: "left",
  padding: "10px 12px",
  borderBottom: `1px solid ${colors.border}`,
  color: colors.muted,
  fontWeight: 600,
  fontSize: 12,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

export const td: React.CSSProperties = {
  padding: "12px",
  borderBottom: `1px solid ${colors.border}`,
  verticalAlign: "top",
};
