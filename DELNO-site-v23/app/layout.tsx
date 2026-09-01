import type { Metadata, Viewport } from "next";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata: Metadata = { title: "DELNO — один ИИ-сотрудник во всех каналах", description: "DELNO принимает звонки, отвечает на сайте и в мессенджерах, ведёт почту и записывает клиентов в одном окне.", keywords: ["ИИ сотрудник","голосовой бот","бот для записи","бот для бизнеса","автоматизация звонков","чат-бот для сайта"], icons:{icon:"/favicon.svg",shortcut:"/favicon.svg"} };
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="ru"><body>{children}</body></html>}
