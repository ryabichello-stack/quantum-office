import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { blogPosts, getBlogPost } from "@/lib/blogPosts";
import { mainPath } from "@/lib/landingPaths";
import { V17PageShell } from "../../v2/v17/V17PageShell";
import { buildDelnoMetadata } from "@/lib/buildMetadata";
import type { Metadata } from "next";
import { LeadFormTrigger } from "@/app/v2/SiteControls";
import { NoShowCalculator } from "@/components/booking/NoShowCalculator";

import "../../v2/dv17.bundle.css";
import "../../v2/v17-overrides.css";
import "../../solutions/booking/solution.css";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const post = getBlogPost(slug);
  if (!post) return {};
  return buildDelnoMetadata({
    title: `${post.title} — блог DELNO`,
    description: post.excerpt,
    path: `/blog/${post.slug}`,
  });
}

const relatedSlugs: Record<string, string[]> = {
  "salon-booking-messages": ["lost-leads-messengers", "no-show-cost", "booking-confirmation-status"],
  "car-service-booking": ["missed-calls-clients", "booking-any-service", "first-response-to-client"],
  "fitness-studio-booking": ["no-show-cost", "waitlist-after-cancellation", "booking-confirmation-status"],
  "clinic-appointment-administration": ["booking-confirmation-status", "first-response-to-client", "online-booking-clients-guide"],
  "voice-bot-for-business": ["missed-calls-clients", "voice-and-chat-one-policy", "pilot-economics-calculation"],
  "telegram-bot-for-business": ["chatbot-for-website-checklist", "lead-processing-automation", "max-bot-for-business"],
  "max-bot-for-business": ["telegram-bot-for-business", "lead-processing-automation", "website-form-or-chat"],
  "ai-administrator-small-business": ["ai-automation-small-business", "bot-vs-administrator-cost", "pilot-economics-calculation"],
  "ai-automation-small-business": ["ai-administrator-small-business", "lead-processing-automation", "pilot-economics-calculation"],
  "booking-system-or-bot": ["online-booking-clients-guide", "booking-any-service", "questions-for-chatbot-contractor"],
};

export default async function BlogPostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = getBlogPost(slug);
  if (!post) notFound();
  const related = (relatedSlugs[post.slug]
    ? relatedSlugs[post.slug].map(getBlogPost).filter((candidate): candidate is NonNullable<typeof candidate> => Boolean(candidate))
    : blogPosts.filter((candidate) => candidate.slug !== post.slug && (
      candidate.category === post.category ||
      (post.slug.includes("booking") && candidate.slug.includes("booking")) ||
      (post.slug.includes("chatbot") && candidate.slug.includes("chatbot"))
    ))).slice(0, 3);

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
            {post.sections?.map((section) => (
              <section className="dc-article-section" key={section.heading}>
                <h2>{section.heading}</h2>
                {section.paragraphs?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                {section.bullets && <ul>{section.bullets.map((item) => <li key={item}>{item}</li>)}</ul>}
                {section.table && <div className="dc-article-table-scroll"><table><thead><tr>{section.table.headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead><tbody>{section.table.rows.map((row) => <tr key={row.join("|")}>{row.map((cell, index) => <td key={`${index}-${cell}`}>{cell}</td>)}</tr>)}</tbody></table></div>}
              </section>
            ))}
          </div>
          {(["no-show-cost", "waitlist-after-cancellation"].includes(post.slug)) && <NoShowCalculator />}
          {post.faqs && <section className="dc-article-faq" aria-labelledby="article-faq-title">
            <h2 id="article-faq-title">Частые вопросы</h2>
            {post.faqs.map((item) => <div key={item.question}><h3>{item.question}</h3><p>{item.answer}</p></div>)}
          </section>}
          {related.length > 0 && <nav className="dc-article-related" aria-label="Статьи по теме">
            <h2>По теме</h2>
            <ul>{related.map((candidate) => <li key={candidate.slug}><Link href={`/blog/${candidate.slug}`}>{candidate.title}</Link></li>)}</ul>
          </nav>}
          <aside className="dc-article-next" aria-label="Следующий шаг">
            <h2>Есть задача, которую стоит проверить?</h2>
            <p>Расскажите, где теряются обращения. Уточним задачу и предложим следующий шаг.</p>
            <LeadFormTrigger className="dv17-button dv17-primary" label="Оставить заявку" source={`blog ${post.slug}`} />
          </aside>
        </article>
      </div>
    </V17PageShell>
  );
}
