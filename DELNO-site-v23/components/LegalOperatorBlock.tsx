import { LEGAL_OPERATOR } from "@/lib/legal-requisites";

/** Compact operator block for /privacy and /terms only — not for the marketing homepage. */
export function LegalOperatorBlock() {
  const o = LEGAL_OPERATOR;
  return (
    <section className="legal-requisites" aria-label="Реквизиты оператора">
      <h2>Оператор / правообладатель</h2>
      <p>
        <strong>{o.shortName}</strong>
        <br />
        ИНН: {o.inn}
        <br />
        ОГРНИП: {o.ogrnip}
        <br />
        Адрес: {o.address}
        <br />
        E-mail:{" "}
        <a href={`mailto:${o.email}`}>{o.email}</a>
        <br />
        Тел.:{" "}
        <a href={`tel:${o.phoneTel}`}>{o.phone}</a>
      </p>
    </section>
  );
}
