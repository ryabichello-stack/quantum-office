"use client";

import Link from "next/link";
import { CalendarDays } from "lucide-react";
import { DashboardFrame } from "@/components/DashboardFrame";

export default function CalendarPage() {
  return (
    <DashboardFrame>
      <div className="page-head">
        <small>DELNO Кабинет</small>
        <h1>Календарь</h1>
        <p>Запись клиентов и слоты — в следующем релизе (E4/E8).</p>
      </div>
      <div className="delno-result stub-panel">
        <CalendarDays style={{ width: 28, height: 28, color: "#bd8900", marginBottom: 12 }} />
        <p style={{ margin: "0 0 12px" }}>
          Сейчас DELNO принимает заявки и ведёт диалоги. Карточки записи появятся здесь, когда подключим booking.
        </p>
        <p style={{ margin: 0 }}>
          <Link href="/dashboard/inbox" style={{ fontWeight: 700 }}>
            Открыть диалоги →
          </Link>
          {" · "}
          <Link href="/dashboard/operator" style={{ fontWeight: 700 }}>
            Настроить через Operator →
          </Link>
        </p>
      </div>
    </DashboardFrame>
  );
}
