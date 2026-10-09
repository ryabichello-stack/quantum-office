import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { V17PageShell } from "../v17/V17PageShell";

export default function V2BlogIndex() {
  return (
    <V17PageShell>
      <div className="dc-content-page">
        <div className="dc-content-wrap">
          <Link href="/v2" className="dv17-inline-link">
            <ArrowLeft size={16} aria-hidden /> На главную V17
          </Link>
          <h1>Блог DELNO</h1>
          <p>Статьи скоро появятся здесь. Пока — материалы с лендинга:</p>
          <ul className="dc-link-list">
            <li>
              <Link href="/v2/blog/one-employee-many-channels">Один ИИ-сотрудник вместо нескольких ботов</Link>
            </li>
            <li>
              <Link href="/v2/blog/prepare-knowledge-base">Что подготовить для первого сценария</Link>
            </li>
          </ul>
        </div>
      </div>
    </V17PageShell>
  );
}
