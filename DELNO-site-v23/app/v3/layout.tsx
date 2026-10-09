import type { Metadata } from "next";
import { buildDelnoMetadata } from "@/lib/buildMetadata";
import "../v2/v2.css";
import "./v3.css";

export const metadata: Metadata = buildDelnoMetadata({
  title: "DELNO — отвечает клиентам во всех каналах",
  description:
    "DELNO принимает звонки и сообщения, отвечает по вашей базе знаний, записывает клиента и сохраняет историю. Предыдущая версия лендинга (v3).",
  path: "/v3",
});

export default function V3Layout({ children }: { children: React.ReactNode }) {
  return <div className="v3-landing">{children}</div>;
}
