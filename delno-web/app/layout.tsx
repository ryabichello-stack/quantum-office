export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, background: "#f8fafc", color: "#0f172a" }}>
        {children}
      </body>
    </html>
  );
}
