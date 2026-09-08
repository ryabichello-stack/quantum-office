import type { Metadata, Viewport } from "next";
import "./globals.css";
import { WidgetHost } from "@/components/widget/WidgetHost";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata: Metadata = { title: "DELNO — отвечает клиентам во всех каналах", description: "DELNO принимает звонки и сообщения, отвечает по вашей базе знаний, записывает клиента и сохраняет результат в одном окне.", keywords: ["ИИ сотрудник","голосовой бот","бот для записи","бот для бизнеса","автоматизация звонков","чат-бот для сайта"], icons:{icon:"/favicon.svg",shortcut:"/favicon.svg"} };
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){
  return (
    <html lang="ru">
      <body>
        {children}
        <WidgetHost />
      </body>
    </html>
  );
}
