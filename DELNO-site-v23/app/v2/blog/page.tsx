import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { V17SiteFooter, V17SiteHeader } from "../v17/SiteChrome";

export default function V2BlogIndex() {
  return (
    <>
      <V17SiteHeader />
      <main className="delno-v17 dc-content-page">
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
      </main>
      <V17SiteFooter />
    </>
  );
}
