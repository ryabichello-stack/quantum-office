"use client";

import { Menu } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

import { mainPath } from "@/lib/landingPaths";

const base = mainPath("/");

export function V17SiteHeader() {
  return (
    <header className="dc-header">
      <div className="dc-header-inner">
        <Link href={base} className="dc-brand" aria-label="DELNO — главная">
          <Image src="/delno-mark.svg" width={28} height={27} alt="" />
          DELNO
        </Link>
        <nav className="dc-top-nav" aria-label="Основная навигация">
          <a href={`${base}#work`}>Как работает</a>
          <Link href={mainPath("/solutions/booking")}>Запись клиентов</Link>
          <a href={`${base}#prices`}>Стоимость</a>
          <Link href={mainPath("/blog")}>Блог</Link>
          <a href={`${base}#contact`}>Контакты</a>
        </nav>
        <a href={`${base}#contact`} className="dc-top-action">
          Оставить заявку
        </a>
        <details className="dc-mobile-menu">
          <summary aria-label="Открыть меню">
            <Menu size={23} aria-hidden />
          </summary>
          <nav aria-label="Мобильная навигация" onClick={(event) => {
            if ((event.target as HTMLElement).closest("a")) {
              event.currentTarget.closest("details")?.removeAttribute("open");
            }
          }}>
            <Link href={base}>Главная</Link>
            <a href={`${base}#work`}>Как работает</a>
            <Link href={mainPath("/solutions/booking")}>Запись клиентов</Link>
            <a href={`${base}#prices`}>Стоимость</a>
            <Link href={mainPath("/blog")}>Блог</Link>
            <a href={`${base}#contact`}>Контакты</a>
          </nav>
        </details>
      </div>
    </header>
  );
}

/** Marketing homepage footer: brand + year only. Requisites live on /privacy and /terms. */
export function V17SiteFooter() {
  return (
    <footer className="dc-footer">
      <div className="dc-footer-inner">
        <div className="dc-footer-bottom dc-footer-bottom--minimal">
          <Link href={base} className="dc-brand">
            <Image src="/delno-mark.svg" width={31} height={30} alt="" />
            DELNO
          </Link>
          <span>© 2026 DELNO</span>
        </div>
      </div>
    </footer>
  );
}
