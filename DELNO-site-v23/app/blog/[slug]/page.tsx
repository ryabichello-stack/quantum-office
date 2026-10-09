import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { blogPosts, getBlogPost } from "@/lib/blogPosts";
import { buildDelnoMetadata } from "@/lib/buildMetadata";
import { mainPath } from "@/lib/landingPaths";
import { getClusterForSlug } from "@/lib/seoBlogCore";
import { V17PageShell } from "../../v2/v17/V17PageShell";

import "../../v2/dv17.bundle.css";
import "../../v2/v17-overrides.css";

export function generateStaticParams() {
  return blogPosts.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const post = getBlogPost(slug);
  if (!post) return {};
  const cluster = getClusterForSlug(slug);
  const keywords = cluster
    ? [cluster.primary.phrase, ...cluster.secondary.map((k) => k.phrase), ...cluster.lsi.map((k) => k.phrase)]
    : post.focusKeyword
      ? [post.focusKeyword]
      : undefined;
  return buildDelnoMetadata({
    title: post.metaTitle ?? `${post.title} — DELNO`,
    description: post.metaDescription ?? post.excerpt,
    path: `/blog/${slug}`,
    keywords,
  });
}

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
