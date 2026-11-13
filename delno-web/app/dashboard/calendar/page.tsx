"use client";

import Link from "next/link";
import { DashboardFrame } from "@/components/DashboardFrame";
import { CabinetCard, CabinetEmpty, CabinetPage } from "@/components/CabinetPage";

export default function CalendarPage() {
  return (
    <DashboardFrame>
      <CabinetPage
        kicker="Скоро"
        title="Календарь"
        lead="Запись клиентов подключим отдельно. Пока всё управление — через Hermes."
      >
        <CabinetCard>
          <CabinetEmpty
            title="Календарь ещё не подключён"
            lead="Когда будет готово — слоты появятся здесь в том же стиле, что и Hermes."
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
        </CabinetCard>
      </CabinetPage>
    </DashboardFrame>
  );
}
