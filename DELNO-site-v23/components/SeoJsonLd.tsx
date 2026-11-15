import { getSiteUrl } from "@/lib/siteUrl";

type Props = {
  /** Override for nested routes (e.g. /v2). */
  path?: string;
};

export function SeoJsonLd({ path = "" }: Props) {
  void path;
  const site = getSiteUrl();

  const org = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "DELNO",
    url: site,
    email: "office@dlno.ru",
    logo: `${site}/delno-mark.svg`,
  };

  const faq = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "Какую работу можно поручить DELNO?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Помогаем отвечать на обращения, собирать заявки и передавать их ответственному. Состав действий согласуем для конкретной задачи.",
        },
      },
      {
        "@type": "Question",
        name: "Что входит в стоимость?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "На сайте указаны ориентиры стоимости. Состав, лимиты, телефонию, настройку и интеграции согласуем до подключения.",
        },
      },
    ],
  };

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(org) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faq) }} />
    </>
  );
}
