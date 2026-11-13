"use client";

import Link from "next/link";
import { CabinetEmpty, CabinetPage } from "@/components/CabinetPage";

export default function InboxIndexPage() {
  return (
    <CabinetPage
      kicker="Каналы"
      title="Диалоги"
      lead="Выберите разговор слева — или откройте Hermes, чтобы начать новый."
    >
      <CabinetEmpty
        title="Выберите диалог"
        lead="Слева — входящие с сайта, Telegram и звонков. Hermes — отдельный рабочий чат владельца."
        action={
          <div className="hx-suggestions" style={{ marginTop: 16 }}>
            <Link href="/dashboard/hermes" className="hx-chip-link">
              Открыть Hermes
            </Link>
            <Link href="/dashboard/leads" className="hx-chip-link">
              Смотреть заявки
            </Link>
          </div>
        }
      />
    </CabinetPage>
  );
}
