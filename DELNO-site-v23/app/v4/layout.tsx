import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DELNO — ваш новый ИИ-сотрудник",
  description: "DELNO отвечает клиентам на сайте, в мессенджерах, по почте и телефону. Консультирует, принимает заявки и записывает 24/7.",
};

export default function V4Layout({ children }: { children: React.ReactNode }) {
  return children;
}
