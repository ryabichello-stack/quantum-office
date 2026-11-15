"use client";

import { ArrowRight, Mic, X } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { reachGoal } from "@/lib/metrikaClient";

const navItems = [
  ["scenarios", "Задачи"],
  ["product", "Продукт"],
  ["solutions", "Возможности"],
  ["prices", "Тарифы"],
  ["answers", "Вопросы"],
  ["contact", "Контакты"],
] as const;

export function ActiveNav() {
  const [active, setActive] = useState("product");
  const navRef = useRef<HTMLElement | null>(null);
  const [pill, setPill] = useState({ left: 0, width: 0 });

  useEffect(() => {
    let frame = 0;
    const update = () => {
      const sections = navItems
        .map(([id]) => document.getElementById(id))
        .filter((item): item is HTMLElement => Boolean(item));
      const marker = window.innerHeight * 0.34;
      const visible = sections.reduce(
        (best, section) => {
          const distance = Math.abs(section.getBoundingClientRect().top - marker);
          return distance < best.distance ? { id: section.id, distance } : best;
        },
        { id: "product", distance: Number.POSITIVE_INFINITY },
      );
      setActive(visible.id);
    };
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  useEffect(() => {
    const link = navRef.current?.querySelector<HTMLElement>(`[data-section="${active}"]`);
    if (link) setPill({ left: link.offsetLeft, width: link.offsetWidth });
  }, [active]);

  return (
    <nav className="section-nav" ref={navRef} aria-label="Разделы страницы">
      <span
        className="section-nav-pill"
        style={{ width: pill.width, transform: `translateX(${pill.left}px)` }}
      />
      {navItems.map(([id, label]) => (
        <a key={id} href={`#${id}`} data-section={id} className={active === id ? "active" : ""}>
          {label}
        </a>
      ))}
    </nav>
  );
}

type LeadFormTriggerProps = {
  label: string;
  className?: string;
  source?: string;
};

type LeadErrorCode =
  | "NAME_AND_PHONE_REQUIRED"
  | "PHONE_INVALID"
  | "VALIDATION_FAILED"
  | "DELNO_API_UNREACHABLE"
  | "DELNO_API_LEAD_FAILED"
  | "LEAD_SUBMIT_FAILED";

function leadErrorMessage(code: LeadErrorCode | string): string {
  switch (code) {
    case "NAME_AND_PHONE_REQUIRED":
      return "Укажите имя и телефон.";
    case "PHONE_INVALID":
      return "Проверьте номер телефона — нужно не меньше 10 цифр.";
    case "VALIDATION_FAILED":
      return "Проверьте поля формы и попробуйте ещё раз.";
    case "DELNO_API_UNREACHABLE":
      return "Сервер временно недоступен. Попробуйте через минуту.";
    default:
      return "Не удалось отправить заявку. Проверьте соединение и попробуйте ещё раз.";
  }
}

export function LeadFormTrigger({
  label,
  className = "lead-trigger",
  source = "Сайт DELNO",
}: LeadFormTriggerProps) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<"idle" | "sending" | "success" | "error">("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const startedRef = useRef(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    setStatus("sending");
    setErrorMessage("");
    const data = new FormData(form);
    try {
      const response = await fetch("/api/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source,
          name: String(data.get("name") || ""),
          phone: String(data.get("phone") || ""),
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as { error?: string };
      if (!response.ok) {
        setErrorMessage(leadErrorMessage(payload.error || "LEAD_SUBMIT_FAILED"));
        setStatus("error");
        return;
      }
      form.reset();
      setStatus("success");
      reachGoal("delno_lead_success");
    } catch {
      setErrorMessage(leadErrorMessage("LEAD_SUBMIT_FAILED"));
      setStatus("error");
    }
  };

  return (
    <>
      <button className={className} type="button" onClick={() => { startedRef.current = false; reachGoal("delno_lead_open"); setOpen(true); }}>
        {label}
        <ArrowRight />
      </button>
      <dialog
        ref={dialogRef}
        className="lead-dialog"
        onClose={() => {
          setOpen(false);
          setStatus("idle");
          setErrorMessage("");
            }}
        onClick={(event) => {
          if (event.target === dialogRef.current) setOpen(false);
        }}
      >
        <button className="lead-close" type="button" onClick={() => setOpen(false)} aria-label="Закрыть форму">
          <X />
        </button>
        <div className="lead-orb">
          <Mic />
        </div>
        {status === "success" ? (
          <div className="lead-success">
            <small>Заявка отправлена</small>
            <h2>
              Спасибо!
              <br />
              DELNO уже получил заявку.
            </h2>
            <p>Свяжемся с вами, чтобы уточнить задачу и предложить следующий шаг.</p>
            <button
              className="lead-submit"
              type="button"
              onClick={() => {
                setOpen(false);
                setStatus("idle");
              }}
            >
              Готово <ArrowRight />
            </button>
          </div>
        ) : (
          <>
            <small>Короткая заявка</small>
            <h2>
              Разберём вашу задачу
              <br />
              и предложим решение.
            </h2>
            <p>Оставьте контакты — уточним сценарий, объём обращений и удобное время для разговора.</p>
            <form onSubmit={submit} onFocusCapture={() => {
              if (!startedRef.current) {
                startedRef.current = true;
                reachGoal("delno_lead_start");
              }
            }}>
              <label>
                Как к вам обращаться
                <input name="name" autoComplete="name" placeholder="Ваше имя" required />
              </label>
              <label>
                Телефон
                <input name="phone" type="tel" autoComplete="tel" placeholder="+7 999 000-00-00" required />
              </label>
              <label className="lead-consent">
                <input name="consent" type="checkbox" required />{" "}
                <span>
                  Согласен на обработку данных по{" "}
                  <a href="/privacy" target="_blank">
                    политике конфиденциальности
                  </a>
                  .
                </span>
              </label>
              <button className="lead-submit" type="submit" disabled={status === "sending"}>
                {status === "sending" ? "Отправляем…" : "Отправить заявку"} <ArrowRight />
              </button>
              {status === "error" && errorMessage && <small className="lead-error">{errorMessage}</small>}
            </form>
          </>
        )}
      </dialog>
    </>
  );
}
