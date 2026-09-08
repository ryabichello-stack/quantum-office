export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, background: "#0b0f14", color: "#e8eef5" }}>
        {children}
      </body>
    </html>
  );
}
