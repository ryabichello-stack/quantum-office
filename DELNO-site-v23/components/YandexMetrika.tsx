import Script from "next/script";

const counterId = (
  process.env.YM_COUNTER_ID ??
  process.env.NEXT_PUBLIC_YM_COUNTER_ID ??
  ""
).trim();

/** Yandex Metrika — loads only when NEXT_PUBLIC_YM_COUNTER_ID is set in env. */
export function YandexMetrika() {
  if (!counterId || !/^\d+$/.test(counterId)) {
    return null;
  }

  const id = Number(counterId);

  return (
    <>
      <Script id="yandex-metrika-init" strategy="afterInteractive">
        {`
(function(m,e,t,r,i,k,a){
  m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
  m[i].l=1*new Date();
  for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
  k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
})(window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

ym(${id}, "init", {
  clickmap: true,
  trackLinks: true,
  accurateTrackBounce: true,
  webvisor: true,
  ecommerce: "dataLayer"
});
        `}
      </Script>
      <noscript>
        <div>
          <img
            src={`https://mc.yandex.ru/watch/${id}`}
            style={{ position: "absolute", left: "-9999px" }}
            alt=""
          />
        </div>
      </noscript>
    </>
  );
}
