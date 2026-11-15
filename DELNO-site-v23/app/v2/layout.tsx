import type { Metadata } from "next";
import { SeoJsonLd } from "@/components/SeoJsonLd";
import { buildDelnoMetadata } from "@/lib/buildMetadata";
import "./dv17.bundle.css";
import "./v17-overrides.css";
import "./v2.css";

export const metadata: Metadata = buildDelnoMetadata({
  title: "DELNO — ИИ-сотрудник: звонки, Telegram, MAX, запись клиентов",
  description:
    "Попробуйте DELNO на сайте: ИИ отвечает по вашим услугам и ценам, ведёт диалог в мессенджерах и записывает клиентов. Демо без регистрации.",
  path: "/v2",
});

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SeoJsonLd path="/v2" />
      {children}
    </>
  );
}
