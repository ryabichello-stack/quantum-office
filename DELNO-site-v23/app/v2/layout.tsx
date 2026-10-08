import type { Metadata } from "next";
import "../v4/v4.css";
import "./convert.css";

export const metadata: Metadata = {
  title: "DELNO — попробуйте ИИ-сотрудника на вашем бизнесе",
  description:
    "Голосовое демо на сайте, прозрачные лимиты пакетов (300 диалогов, 30 мин голоса, 100 мин телефонии). Запись и заявки 24/7.",
};

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return children;
}
