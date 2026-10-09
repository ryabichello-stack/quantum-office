import type { Metadata } from "next";
import "./dv17.bundle.css";
import "./v17-overrides.css";
import "./v2.css";

export const metadata: Metadata = {
  title: "DELNO V17 — ИИ-сотрудник для звонков и сообщений",
  description:
    "Знает ваши услуги, цены и правила. Отвечает клиентам, создаёт записи и звонит за вас — 24/7.",
  keywords: [
    "ИИ сотрудник",
    "голосовой бот",
    "бот для записи",
    "бот для бизнеса",
    "автоматизация звонков",
    "чат-бот для сайта",
  ],
};

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return children;
}
