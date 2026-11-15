import {ArrowLeft, ArrowRight, Check} from "lucide-react";
import "./logo3.css";

function DelnoGlyph({className = ""}:{className?:string}) {
  return (
    <svg className={`delno-glyph ${className}`} viewBox="0 0 84 84" role="img" aria-label="Фирменный знак DELNO">
      <path fillRule="evenodd" d="M7 7h36c21 0 35 14 35 35S64 77 43 77H7V39h19v19h17c10 0 16-6 16-16s-6-16-16-16H7V7Z"/>
    </svg>
  );
}

function Wordmark({inverse=false, compact=false}:{inverse?:boolean;compact?:boolean}) {
  return (
    <div className={`wordmark3 ${inverse ? "inverse" : ""} ${compact ? "compact" : ""}`} aria-label="delno">
      <DelnoGlyph/><span>ELNO</span>
    </div>
  );
}

export default function LogoThree() {
  return <main className="logo3">
    <header className="topbar3">
      <a href="/v2"><ArrowLeft/> К сайту</a>
      <span>DELNO · фирменный знак</span>
      <nav><a href="/logo">01</a><b>03</b></nav>
    </header>

    <section className="hero3">
      <div className="hero-index">Направление 03</div>
      <Wordmark/>
      <div className="hero-copy">
        <h1>Сила без шума.<br/>Технологии без сложности.</h1>
        <p>Монолитная D говорит о надёжной платформе. Точный разрыв в левой стойке делает знак собственным, а строгий набор DELNO фиксирует бренд как имя большого цифрового сервиса.</p>
      </div>
      <div className="hero-rule"><span>Слово важнее символа</span><i/><span>2026</span></div>
    </section>

    <section className="principle3">
      <div className="principle-title"><span>01 / принцип</span><h2>Узнаваемость<br/>без украшений.</h2></div>
      <div className="principle-copy">
        <p className="lead">Знак не пытается изобразить звонок, чат или ИИ. Он закрепляет в памяти одно короткое имя — <b>DELNO</b>.</p>
        <div className="checks">
          <p><Check/> читается одинаково в интерфейсе и рекламе</p>
          <p><Check/> выглядит естественно рядом с русским текстом</p>
          <p><Check/> не зависит от фирменного цвета</p>
        </div>
      </div>
    </section>

    <section className="construction3">
      <div className="construction-mark"><div className="measure m1">01</div><div className="measure m2">02</div><DelnoGlyph/></div>
      <div className="construction-copy">
        <span>02 / конструкция</span>
        <h2>Цельная форма.<br/>Точный разрыв.<br/>Свой характер.</h2>
        <p>Верхняя горизонталь переходит в мощную дугу D. Отделённая нижняя стойка создаёт узнаваемый ритм и лёгкую отсылку к кириллической конструкции — без буквального изображения «Д».</p>
        <div className="micro"><DelnoGlyph/><span>16</span><DelnoGlyph/><span>24</span><DelnoGlyph/><span>32</span></div>
      </div>
    </section>

    <section className="color3">
      <article className="cream"><small>Светлое поле</small><Wordmark/></article>
      <article className="ink"><small>Тёмное поле</small><Wordmark inverse/></article>
      <article className="signal"><small>Сигнальный цвет</small><Wordmark/></article>
    </section>

    <section className="use3">
      <div className="use-heading"><span>03 / в продукте</span><h2>Это уже похоже<br/>на сервис.</h2></div>
      <div className="product-shell">
        <aside><Wordmark inverse compact/><div className="side-nav"><b>Обращения</b><span>Клиенты</span><span>Знания</span><span>Рассылки</span></div><i>D</i></aside>
        <div className="product-main">
          <header><span>Обращения</span><button>Подключить канал</button></header>
          <div className="dialog-row active"><div className="avatar yellow">А</div><p><b>Анна Лебедева</b><span>Хочу перенести запись на пятницу</span></p><time>10:42</time></div>
          <div className="dialog-row"><div className="avatar">МС</div><p><b>Михаил Соколов</b><span>Входящий звонок · 3:12</span></p><time>10:18</time></div>
          <div className="dialog-row"><div className="avatar">ЕК</div><p><b>Елена К.</b><span>Спасибо, всё получилось</span></p><time>09:55</time></div>
        </div>
      </div>
      <div className="app-tile"><div className="tile"><DelnoGlyph/></div><div><b>DELNO</b><span>Все обращения — в одном месте</span></div></div>
    </section>

    <section className="verdict3">
      <span>Третье направление</span>
      <h2>Знак, который выдержит<br/>масштаб большого сервиса.</h2>
      <p>Эта версия строже и увереннее предыдущих. Она одинаково естественно выглядит в приложении, на сайте, в рекламе и на физической вывеске.</p>
      <div><a href="/logo">Сравнить с первым <ArrowLeft/></a><a href="/v2">Вернуться к сайту <ArrowRight/></a></div>
    </section>
  </main>;
}
