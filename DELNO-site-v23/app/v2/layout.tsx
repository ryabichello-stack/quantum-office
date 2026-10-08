import type { Metadata } from "next";
import "../v4/v4.css";
import "./convert.css";
import "./convert-landing.css";

export const metadata: Metadata = {
  title: "DELNO — нанять ИИ-сотрудника на первую линию",
  description:
    "Живое голосовое демо, тарифы от 2 990 ₽. DELNO отвечает клиентам на сайте, в мессенджерах и по телефону — 24/7.",
};

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return children;
}
