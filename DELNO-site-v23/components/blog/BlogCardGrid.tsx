import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import type { BlogPost } from "@/lib/blogPosts";
import { mainPath } from "@/lib/landingPaths";

type Props = {
  posts: BlogPost[];
};

export function BlogCardGrid({ posts }: Props) {
  return (
    <div className="dv17-blog-preview-cards dc-blog-grid">
      {posts.map((post) => (
        <Link key={post.slug} href={mainPath(`/blog/${post.slug}`)}>
          <span>{post.category}</span>
          <strong>{post.title}</strong>
          <ArrowUpRight size={18} aria-hidden />
        </Link>
      ))}
    </div>
  );
}
