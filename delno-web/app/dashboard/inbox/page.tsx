"use client";

import { MessageCircle } from "lucide-react";

export default function InboxIndexPage() {
  return (
    <>
      <div className="page-head">
        <small>Рабочее пространство</small>
        <h1>Диалоги</h1>
        <p>Выберите диалог слева или начните новый в Operator</p>
      </div>
      <div className="delno-result" style={{ textAlign: "center", padding: 32 }}>
        <MessageCircle style={{ width: 28, height: 28, color: "#bd8900", marginBottom: 12 }} />
        <p style={{ margin: 0, color: "#777" }}>История разговоров Operator и каналов</p>
      </div>
    </>
  );
}
