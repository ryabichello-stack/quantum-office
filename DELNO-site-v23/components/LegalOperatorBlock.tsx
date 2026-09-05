import { LEGAL_OPERATOR } from "@/lib/legal-requisites";

export function LegalOperatorBlock() {
  const o = LEGAL_OPERATOR;
  return (
    <section className="legal-requisites" aria-label="Реквизиты оператора">
      <h2>Оператор / правообладатель</h2>
      <p>
        <strong>{o.shortName}</strong>
        <br />
        {o.fullName}
        <br />
        ИНН: {o.inn}
        <br />
        ОГРНИП: {o.ogrnip}
        <br />
        Адрес: {o.address}
        <br />
        ОКВЭД: {o.okved}
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
