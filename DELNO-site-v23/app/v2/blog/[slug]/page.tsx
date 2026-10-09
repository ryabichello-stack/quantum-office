import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { V17PageShell } from "../../v17/V17PageShell";

const posts: Record<string, { title: string; body: string[] }> = {
  "one-employee-many-channels": {
    title: "Один ИИ-сотрудник вместо нескольких ботов",
    body: [
      "Клиенты пишут в Telegram, звонят, пишут на почту — а ответы разъезжаются по разным сервисам. DELNO держит одну базу знаний и одну историю обращения.",
      "Вы подключаете только нужные каналы и одну задачу на старте: ответы, запись или подтверждение визитов.",
    ],
  },
  "prepare-knowledge-base": {
    title: "Что подготовить для первого сценария",
    body: [
      "Для запуска достаточно сайта или прайса, списка услуг и правил работы (график, запись, что DELNO может и не может решать сам).",
      "Мы поможем оформить это в базу знаний и проверить ответы до включения телефонии.",
    ],
  },
};

export default async function V2BlogPost({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = posts[slug];
  if (!post) notFound();

  return (
    <V17PageShell>
      <div className="dc-content-page">
        <article className="dc-content-wrap">
          <Link href="/v2/blog" className="dv17-inline-link">
            <ArrowLeft size={16} aria-hidden /> Все статьи
          </Link>
          <h1>{post.title}</h1>
          {post.body.map((p) => (
            <p key={p.slice(0, 24)}>{p}</p>
          ))}
        </article>
      </div>
    </V17PageShell>
  );
}
