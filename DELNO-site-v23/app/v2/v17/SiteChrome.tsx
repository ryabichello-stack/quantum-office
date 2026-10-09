import { ArrowUpRight, Menu } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

const base = "/v2";

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
          <a href={`${base}#prices`}>Стоимость</a>
          <Link href={`${base}/blog`}>Блог</Link>
          <Link href={`${base}/help`}>Инструкция</Link>
          <a href={`${base}#contact`}>Контакты</a>
        </nav>
        <a href={`${base}#demo`} className="dc-top-action">
          Попробовать
        </a>
        <details className="dc-mobile-menu">
          <summary aria-label="Открыть меню">
            <Menu size={23} aria-hidden />
          </summary>
          <nav aria-label="Мобильная навигация">
            <Link href={base}>Главная</Link>
            <a href={`${base}#work`}>Как работает</a>
            <a href={`${base}#prices`}>Стоимость</a>
            <Link href={`${base}/blog`}>Блог</Link>
            <Link href={`${base}/help`}>Инструкция</Link>
            <a href={`${base}#contact`}>Контакты</a>
          </nav>
        </details>
      </div>
    </header>
  );
}

export function V17SiteFooter() {
  return (
    <footer className="dc-footer">
      <div className="dc-footer-inner">
        <div className="dc-footer-grid">
          <div className="dc-footer-about">
            <Link href={base} className="dc-brand">
              <Image src="/delno-mark.svg" width={31} height={30} alt="" />
              DELNO
            </Link>
            <p>Один ИИ-сотрудник для звонков, сообщений и записи клиентов. На связи 24/7.</p>
            <a href={`${base}#demo`} className="dc-footer-action">
              Попробовать DELNO <ArrowUpRight size={17} aria-hidden />
            </a>
          </div>
          <nav aria-label="Продукт">
            <strong>Продукт</strong>
            <a href={`${base}#work`}>Как работает</a>
            <a href={`${base}#scenarios`}>Сценарии</a>
            <a href={`${base}#prices`}>Стоимость</a>
            <a href={`${base}#demo`}>Попробовать демо</a>
          </nav>
          <nav aria-label="Материалы">
            <strong>Материалы</strong>
            <Link href={`${base}/blog`}>Блог</Link>
            <Link href={`${base}/help`}>Как пользоваться</Link>
            <a href={`${base}#answers`}>Вопросы и ответы</a>
          </nav>
          <div className="dc-footer-contact">
            <strong>Связаться</strong>
            <a className="dc-footer-email" href="mailto:office@dlno.ru">
              office@dlno.ru
            </a>
            <span>8 800 555-00-00</span>
            <small>Бесплатный номер для демо и заявок</small>
            <div>
              <a href="https://t.me/Dlno_bot" target="_blank" rel="noreferrer">
                Telegram <ArrowUpRight size={13} aria-hidden />
              </a>
              <a href="https://max.ru/@id471405233378_bot" target="_blank" rel="noreferrer">
                MAX <ArrowUpRight size={13} aria-hidden />
              </a>
            </div>
          </div>
        </div>
        <div className="dc-footer-bottom">
          <span>© 2026 DELNO</span>
          <div>
            <Link href="/privacy">Конфиденциальность</Link>
            <Link href="/terms">Пользовательское соглашение</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
