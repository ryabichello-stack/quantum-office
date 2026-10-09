import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { BlogCardGrid } from "@/components/blog/BlogCardGrid";
import { blogPosts } from "@/lib/blogPosts";
import { mainPath } from "@/lib/landingPaths";
import { V17PageShell } from "../v2/v17/V17PageShell";

import "../v2/dv17.bundle.css";
import "../v2/v17-overrides.css";

export default function BlogIndexPage() {
  return (
    <V17PageShell className="delno-v17-blog-index">
      <div className="dc-content-page dc-blog-index">
        <div className="dc-content-wrap dc-blog-index-inner">
          <Link href={mainPath("/")} className="dv17-inline-link">
            <ArrowLeft size={16} aria-hidden /> На главную
          </Link>
          <p className="dv17-eyebrow dc-blog-eyebrow">Блог DELNO</p>
          <h1>Как поручить рутину ИИ и сохранить качество сервиса</h1>
          <p className="dc-blog-lead">
            Сценарии, база знаний и запуск ИИ-сотрудника — без лишней терминологии. Выберите статью и
            переходите к полному тексту.
          </p>
          <BlogCardGrid posts={blogPosts} />
        </div>
      </div>
    </V17PageShell>
  );
}
