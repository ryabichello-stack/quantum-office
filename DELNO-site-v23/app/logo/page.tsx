import {ArrowLeft,Check} from "lucide-react";
import "./logo.css";

function HybridMark({className=""}:{className?:string}){
  return <svg className={`hybrid-mark ${className}`} viewBox="0 0 72 72" aria-label="Фирменный знак DELNO — гибрид D и Д">
    <path className="glyph" fillRule="evenodd" d="M7 7h27c18.8 0 31 10 31 25.5 0 11.1-6.3 19.4-17 23.2h19V64h-7v7H49v-7H21v7H10v-7H3v-8.3h9V7H7Zm19 13-5 24h12c11.2 0 17.5-4.1 17.5-11.5S44.2 20 33 20h-7Z"/>
  </svg>
}
function Wordmark({light=false,className=""}:{light?:boolean,className?:string}){
  return <div className={`master-wordmark ${light?"is-light":""} ${className}`}><HybridMark/><span>ELNO</span></div>
}

export default function LogoDirection(){
  return <main className="logo-master">
    <header className="master-header"><a href="/v2"><ArrowLeft/> К сайту</a><span>DELNO · Фирменный знак</span><b>Направление 01</b></header>

    <section className="master-hero">
      <div className="master-tag">Не иконка. Первая буква бренда.</div>
      <Wordmark/>
      <h1>Один знак.<br/>Два прочтения.</h1>
      <p>Латинская D делает название международным. Характерные опоры кириллической Д возвращают его к слову «Дельно». Знак не стоит рядом с названием — он начинает его.</p>
    </section>

    <section className="mark-anatomy">
      <div className="anatomy-copy"><span>01 · Конструкция</span><h2>Не объясняет.<br/>Узнаётся.</h2><p>Мы убрали чат, волны, роботов и другие буквальные метафоры. Смысл продукта будет жить в коммуникации, а логотип должен владеть одной простой формой.</p><ul><li><Check/> читается как DELNO на латинице</li><li><Check/> напоминает «Дельно» русскому глазу</li><li><Check/> работает одним цветом</li><li><Check/> сохраняется в 16 пикселях</li></ul></div>
      <div className="anatomy-board">
        <div className="grid-lines" aria-hidden="true"/>
        <HybridMark/>
        <span className="callout c1">Латинская D</span><span className="callout c2">Опоры кириллической Д</span><span className="callout c3">Открытый просвет</span>
      </div>
    </section>

    <section className="brand-fields">
      <div className="field white"><small>Основной</small><Wordmark/></div>
      <div className="field black"><small>Инверсия</small><Wordmark light/></div>
      <div className="field yellow"><small>Фирменное поле</small><Wordmark/></div>
    </section>

    <section className="application">
      <div className="app-head"><span>02 · Проверка в работе</span><h2>От 16 пикселей<br/>до фасада.</h2></div>
      <div className="app-grid">
        <article className="app-icon"><div className="icon-tile"><HybridMark/></div><div><b>DELNO</b><span>ИИ-сотрудник</span></div></article>
        <article className="browser"><div className="browser-top"><i/><i/><i/><span>delno.one</span></div><nav><Wordmark/><div>Продукт&nbsp;&nbsp;&nbsp; Тарифы&nbsp;&nbsp;&nbsp; <b>Попробовать</b></div></nav><h3>Клиенты пишут<br/>и звонят.<br/><mark>DELNO отвечает.</mark></h3></article>
        <article className="small-sizes"><span>Знак в интерфейсе</span><div><HybridMark className="s16"/><HybridMark className="s24"/><HybridMark className="s32"/><HybridMark className="s48"/></div><small>16&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;24&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;32&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;48 px</small></article>
        <article className="voice-card"><Wordmark light/><p>«Здравствуйте. Это DELNO.<br/>Чем могу помочь?»</p><div className="wave">{Array.from({length:18}).map((_,i)=><i key={i}/>)}</div></article>
      </div>
    </section>

    <section className="decision">
      <span>Решение</span><h2>Дальше — не новый эскиз.<br/>Дальше — доводка формы.</h2><p>Если направление верное, следующим шагом выстраиваем оптические пропорции, кернинг ELNO и окончательную геометрию знака. Только после этого переносим его на сайт.</p><a href="/v2">Вернуться к сайту <ArrowLeft/></a>
    </section>
  </main>
}
