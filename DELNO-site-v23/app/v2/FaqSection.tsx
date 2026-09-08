"use client";

import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";

export type FaqItem = [string, string];

type FaqSectionProps = {
  fallback: FaqItem[];
  version4?: boolean;
};

export function FaqSection({ fallback, version4 = false }: FaqSectionProps) {
  const [items, setItems] = useState<FaqItem[]>(fallback);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/cms/faq")
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => {
        if (cancelled || !data?.blocks?.sections?.length) return;
        const parsed: FaqItem[] = data.blocks.sections
          .filter((section: { q?: string; a?: string }) => section.q && section.a)
          .map((section: { q: string; a: string }) => [section.q, section.a]);
        if (parsed.length) setItems(parsed);
      })
      .catch(() => {
        /* keep static fallback */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="v2-faq" id="answers">
      <div>
        <div className="v2-kicker">{version4 ? "Коротко о важном" : "Вопросы"}</div>
        <h2>
          {version4 ? (
            <>
              Вопросы
              <br />
              до запуска.
            </>
          ) : (
            <>
              Всё
              <br />
              по делу.
            </>
          )}
        </h2>
      </div>
      <div>
        {items.map(([question, answer], index) => (
          <details key={`${question}-${index}`} open={index === 0}>
            <summary>
              {question}
              <ChevronRight />
            </summary>
            <p>{answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
