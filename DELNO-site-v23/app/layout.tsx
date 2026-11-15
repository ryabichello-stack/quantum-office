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
  title: "DELNO — ИИ-сотрудник для обработки заявок и записи клиентов",
  description:
    "Как не терять обращения и заявки на запись: сценарии для малого бизнеса, расчёты потерь и способы обработки заявок с DELNO. Оставьте заявку.",
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
