import type { Viewport } from "next";
import "./globals.css";
import { SeoJsonLd } from "@/components/SeoJsonLd";
import { YandexMetrika } from "@/components/YandexMetrika";
import { WidgetHost } from "@/components/widget/WidgetHost";
import { buildDelnoMetadata } from "@/lib/buildMetadata";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata = buildDelnoMetadata({
  title: "DELNO — ИИ-сотрудник для звонков, чатов и записи клиентов",
  description:
    "DELNO принимает звонки и сообщения, отвечает по вашей базе знаний, записывает клиентов и работает 24/7. Тарифы от 2 990 ₽/мес.",
  path: "/",
});

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>
        <SeoJsonLd path="/" />
        {children}
        <WidgetHost />
        <YandexMetrika />
      </body>
    </html>
  );
}
