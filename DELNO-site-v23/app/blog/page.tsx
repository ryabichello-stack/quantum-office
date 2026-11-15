import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { BlogCardGrid } from "@/components/blog/BlogCardGrid";
import { blogPosts } from "@/lib/blogPosts";
import { mainPath } from "@/lib/landingPaths";
import { V17PageShell } from "../v2/v17/V17PageShell";
import { buildDelnoMetadata } from "@/lib/buildMetadata";

import "../v2/dv17.bundle.css";
import "../v2/v17-overrides.css";

export const metadata = buildDelnoMetadata({
  title: "Блог DELNO — заявки, запись клиентов, чат-боты и экономика",
  description: "Практические инструкции, таблицы и расчёты для малого бизнеса: как не терять обращения, вести запись, выбирать каналы и считать стоимость решения.",
  path: "/blog",
});

const groups = [
  { id: "inquiries", title: "Обращения и потерянные заявки", categories: ["Потери заявок", "Обращения"] },
  { id: "booking", title: "Запись, перенос и неявки", categories: ["Запись"] },
  { id: "channels", title: "Каналы связи и голос", categories: ["Каналы", "Звонки", "Сценарии"] },
  { id: "industries", title: "Для разных отраслей", categories: ["Для салонов", "Для автосервиса", "Для студий", "Для клиник"] },
  { id: "selection", title: "Цена и выбор решения", categories: ["Цена и выбор", "Выбор решения"] },
  { id: "start", title: "Подготовка и запуск", categories: ["Основа", "Практика", "Запуск"] },
];

export default function BlogIndexPage() {
  return (
    <V17PageShell className="delno-v17-blog-index">
      <div className="dc-content-page dc-blog-index">
        <div className="dc-content-wrap dc-blog-index-inner">
          <Link href={mainPath("/")} className="dv17-inline-link">
            <ArrowLeft size={16} aria-hidden /> На главную
          </Link>
          <p className="dv17-eyebrow dc-blog-eyebrow">Блог DELNO</p>
          <h1>Как не терять обращения и доводить их до результата</h1>
          <p className="dc-blog-lead">
            Практические разборы для малого бизнеса: запись, ответы клиентам, стоимость решений и проверка
            экономики. Выберите задачу и начните с полезного материала.
          </p>
          <nav className="dc-blog-topics" aria-label="Темы блога">
            {groups.map((group) => <a key={group.id} href={`#${group.id}`}>{group.title}</a>)}
          </nav>
          {groups.map((group) => {
            const posts = blogPosts.filter((post) => group.categories.includes(post.category))
              .sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));
            return <section className="dc-blog-topic" id={group.id} key={group.id}>
              <h2>{group.title}</h2>
              <BlogCardGrid posts={posts} />
            </section>;
          })}
        </div>
      </div>
    </V17PageShell>
  );
}
