import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getBlogPost } from "@/lib/blogPosts";
import { mainPath } from "@/lib/landingPaths";
import { V17PageShell } from "../../v2/v17/V17PageShell";

import "../../v2/dv17.bundle.css";
import "../../v2/v17-overrides.css";

export default async function BlogPostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = getBlogPost(slug);
  if (!post) notFound();

  return (
    <V17PageShell>
      <div className="dc-content-page">
        <article className="dc-content-wrap dc-blog-article">
          <Link href={mainPath("/blog")} className="dv17-inline-link">
            <ArrowLeft size={16} aria-hidden /> Все статьи
          </Link>
          <p className="dc-blog-meta">
            <span>{post.category}</span>
            <span aria-hidden>·</span>
            <time dateTime={post.publishedAt}>
              {new Date(post.publishedAt).toLocaleDateString("ru-RU", {
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </time>
            <span aria-hidden>·</span>
            <span>{post.readMinutes} мин чтения</span>
          </p>
          <h1>{post.title}</h1>
          <p className="dc-blog-excerpt">{post.excerpt}</p>
          <div className="dc-blog-body">
            {post.body.map((paragraph) => (
              <p key={paragraph.slice(0, 32)}>{paragraph}</p>
            ))}
          </div>
        </article>
      </div>
    </V17PageShell>
  );
}
