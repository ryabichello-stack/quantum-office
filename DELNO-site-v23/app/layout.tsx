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
  title: "DELNO — ИИ-сотрудник: звонки, Telegram, MAX, запись клиентов",
  description:
    "Попробуйте DELNO на сайте: ИИ отвечает по вашим услугам и ценам, ведёт диалог в мессенджерах и записывает клиентов. Демо без регистрации.",
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
