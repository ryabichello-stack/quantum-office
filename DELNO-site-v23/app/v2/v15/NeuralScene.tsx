"use client";

import {
  ArrowRight,
  Calendar,
  Check,
  Database,
  Mail,
  Phone,
  PhoneIncoming,
  PhoneOutgoing,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useLayoutEffect, useRef, useState } from "react";
import {
  neuralChannels,
  outboundPhoneScenario,
  type NeuralChannel,
  type NeuralChannelId,
} from "./neuralChannels";

type WirePoint = { x: number; y: number };
type WireSegment = { start: WirePoint; end: WirePoint };
type WireLayout = {
  width: number;
  height: number;
  inputs: WireSegment[];
  output: WireSegment;
};

const outerNodes = Array.from({ length: 12 }, (_, t) => {
  const n = -Math.PI + t * (Math.PI / 6);
  return { x: 110 + 77 * Math.cos(n), y: 105 + 73 * Math.sin(n) };
});

const innerNodes = Array.from({ length: 6 }, (_, t) => {
  const n = -Math.PI + t * (Math.PI / 3);
  return { x: 110 + 47 * Math.cos(n), y: 105 + 44 * Math.sin(n) };
});

function wirePath({ start, end }: WireSegment) {
  const n = Math.max(14, (end.x - start.x) * 0.42);
  return `M ${start.x} ${start.y} C ${start.x + n} ${start.y}, ${end.x - n} ${end.y}, ${end.x} ${end.y}`;
}

function ChannelIcon({ channel, size = 20 }: { channel: NeuralChannel; size?: number }) {
  if (channel.Icon) {
    const Icon = channel.Icon;
    return <Icon size={size} strokeWidth={1.9} aria-hidden />;
  }
  return (
    <Image src={`/channels/${channel.id}.svg`} alt="" width={23} height={23} aria-hidden />
  );
}

export default function NeuralScene() {
  const [activeId, setActiveId] = useState<NeuralChannelId>("phone");
  const [callMode, setCallMode] = useState<"incoming" | "outgoing">("incoming");
  const canvasRef = useRef<HTMLDivElement>(null);
  const coreRef = useRef<HTMLDivElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);
  const channelRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [wires, setWires] = useState<WireLayout | null>(null);

  const active = neuralChannels.find((c) => c.id === activeId)!;
  const isOutboundPhone = activeId === "phone" && callMode === "outgoing";
  const scenario = isOutboundPhone ? outboundPhoneScenario : active;

  useLayoutEffect(() => {
    const canvas = canvasRef.current;
    const core = coreRef.current;
    const output = outputRef.current;
    if (!canvas || !core || !output) return;

    const measure = () => {
      const box = canvas.getBoundingClientRect();
      const coreBox = core.getBoundingClientRect();
      const outputBox = output.getBoundingClientRect();
      const origin = { x: coreBox.left - box.left, y: coreBox.top - box.top + coreBox.height / 2 };
      const coreIn = { x: coreBox.left - box.left, y: origin.y };
      const outStart = { x: coreBox.right - box.left, y: origin.y };
      const outEnd = { x: outputBox.left - box.left, y: outputBox.top - box.top + outputBox.height / 2 };

      const inputs = channelRefs.current.slice(0, neuralChannels.length).map((el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
          start: { x: r.right - box.left, y: r.top - box.top + r.height / 2 },
          end: coreIn,
        };
      }).filter((s): s is WireSegment => s !== null);

      setWires({
        width: box.width,
        height: box.height,
        inputs,
        output: { start: outStart, end: outEnd },
      });
    };

    const ro = new ResizeObserver(measure);
    [canvas, core, output, ...channelRefs.current].forEach((el) => el && ro.observe(el));
    measure();
    return () => ro.disconnect();
  }, [activeId, callMode]);

  return (
    <div
      className="dv15-neural-scene"
      aria-label="Как работает ИИ-сотрудник DELNO"
      style={{ "--signal-color": active.color } as React.CSSProperties}
    >
      <div className="dv15-neural-canvas" ref={canvasRef}>
        {wires && (
          <svg className="dv15-neural-wires" viewBox={`0 0 ${wires.width} ${wires.height}`} aria-hidden>
            {wires.inputs.map((seg, i) => (
              <path
                key={`in-${neuralChannels[i]?.id}`}
                className={activeId === neuralChannels[i]?.id ? "is-active" : ""}
                d={wirePath(seg)}
              />
            ))}
            <path className="is-active dv15-neural-output-wire" d={wirePath(wires.output)} />
          </svg>
        )}

        <div className="dv15-neural-input">
          <div className="dv15-neural-caption">
            <span>01</span> Клиенты обращаются
          </div>
          <div className="dv15-neural-channels" role="group" aria-label="Примеры каналов общения">
            {neuralChannels.map((channel, index) => (
              <button
                key={channel.id}
                type="button"
                ref={(el) => {
                  channelRefs.current[index] = el;
                }}
                className={`dv15-neural-channel ${activeId === channel.id ? "is-active" : ""}`}
                style={{ "--channel-color": channel.color } as React.CSSProperties}
                aria-pressed={activeId === channel.id}
                onClick={() => setActiveId(channel.id)}
              >
                <span className={`dv15-neural-channel-icon dv15-neural-${channel.id}`}>
                  <ChannelIcon channel={channel} />
                </span>
                <span>{channel.name}</span>
                <ArrowRight size={13} className="dv15-channel-chevron" aria-hidden />
              </button>
            ))}
          </div>
          <span className="dv15-neural-more">Другие каналы — по запросу</span>
        </div>

        <div className="dv15-neural-center">
          <div className="dv15-neural-caption">
            <span>02</span> Единая база знаний
          </div>
          <div className="dv15-neural-core" ref={coreRef}>
            <svg className="dv15-core-network" viewBox="0 0 220 210" aria-hidden>
              <circle cx="110" cy="105" r="76" fill="none" stroke="#dbe6f5" strokeWidth="1" />
              <g stroke="#9ab7db" strokeWidth="0.9" opacity="0.62">
                {outerNodes.map((node, t) => (
                  <g key={t}>
                    <line
                      x1={node.x}
                      y1={node.y}
                      x2={outerNodes[(t + 1) % outerNodes.length].x}
                      y2={outerNodes[(t + 1) % outerNodes.length].y}
                    />
                    <line
                      x1={node.x}
                      y1={node.y}
                      x2={innerNodes[Math.floor(t / 2)].x}
                      y2={innerNodes[Math.floor(t / 2)].y}
                    />
                  </g>
                ))}
                {innerNodes.map((node, t) => (
                  <line
                    key={`inner-${t}`}
                    x1={node.x}
                    y1={node.y}
                    x2={innerNodes[(t + 1) % innerNodes.length].x}
                    y2={innerNodes[(t + 1) % innerNodes.length].y}
                  />
                ))}
                <line x1="0" y1="105" x2="34" y2="105" />
                <line x1="186" y1="105" x2="220" y2="105" />
              </g>
              {outerNodes.map((node, t) => (
                <circle key={`outer-${t}`} cx={node.x} cy={node.y} r="2.6" fill={t % 3 === 0 ? "#6d96cb" : "#9bb6d9"} />
              ))}
              {innerNodes.map((node, t) => (
                <circle key={`inner-dot-${t}`} cx={node.x} cy={node.y} r="3.4" fill="#678dc1" />
              ))}
            </svg>
            <span className="dv15-core-port dv15-core-port-in" aria-hidden />
            <div className="dv15-core-brand">
              <strong>DELNO</strong>
              <span>ИИ-сотрудник</span>
            </div>
            <span className="dv15-core-port dv15-core-port-out" aria-hidden />
          </div>
          <div className="dv15-neural-core-copy">
            <strong>Память вашего бизнеса</strong>
            <span>Услуги · цены · правила</span>
          </div>
          <div className="dv15-neural-integrations">
            <span>
              <Calendar size={13} aria-hidden /> Календарь
            </span>
            <span>
              <Database size={13} aria-hidden /> CRM
            </span>
          </div>
          <small className="dv15-neural-integration-note">Системы записи — по задаче</small>
        </div>

        <div className="dv15-neural-output">
          <div className="dv15-neural-caption">
            <span>03</span> Отвечает и вносит запись
          </div>
          <div className="dv15-neural-example" ref={outputRef} aria-live="polite" aria-atomic="true">
            <div className="dv15-neural-example-top">
              <span>Клиенту в канале</span>
              <div className="dv15-neural-out-channels" aria-label="Каналы ответа">
                {neuralChannels.map((channel) => (
                  <span
                    key={channel.id}
                    className={`dv15-neural-channel-icon dv15-neural-${channel.id} ${activeId === channel.id ? "is-active" : ""}`}
                    role="img"
                    aria-label={channel.name}
                    title={channel.name}
                    style={{ "--channel-color": channel.color } as React.CSSProperties}
                  >
                    <ChannelIcon channel={channel} />
                  </span>
                ))}
              </div>
            </div>
            <div className="dv15-neural-business">
              <span className="dv15-example-indicator" style={{ background: active.color }} />
              {scenario.business}
            </div>
            {activeId === "phone" && (
              <div className="dv15-neural-call-switch" role="group" aria-label="Направление звонка">
                <button type="button" aria-pressed={!isOutboundPhone} onClick={() => setCallMode("incoming")}>
                  <PhoneIncoming size={13} aria-hidden />
                  Принимает
                </button>
                <button type="button" aria-pressed={isOutboundPhone} onClick={() => setCallMode("outgoing")}>
                  <PhoneOutgoing size={13} aria-hidden />
                  Звонит сам
                </button>
              </div>
            )}
            <div className="dv15-neural-exchange">
              <div className="dv15-neural-client">
                <small>{isOutboundPhone ? "DELNO звонит" : "Клиент обращается"}</small>
                <p>{isOutboundPhone ? scenario.reply : scenario.customer}</p>
              </div>
              <div className="dv15-neural-reply">
                <small>
                  {isOutboundPhone ? "Клиент отвечает" : "DELNO отвечает"} <Check size={12} aria-hidden />
                </small>
                <p>{isOutboundPhone ? scenario.customer : scenario.reply}</p>
              </div>
            </div>
            <div className="dv15-neural-result">
              <Mail size={14} aria-hidden />
              <span>
                <strong>{scenario.result}</strong>
                <small>{scenario.detail}</small>
              </span>
              {activeId === "phone" && <Calendar className="dv15-result-system-icon" size={15} aria-label="Календарь" />}
            </div>
          </div>
        </div>

        <ArrowRight className="dv15-mobile-flow dv15-mobile-flow-first" size={18} aria-hidden />
        <ArrowRight className="dv15-mobile-flow dv15-mobile-flow-second" size={18} aria-hidden />
      </div>

      <div className="dv15-neural-foot">
        <span>Одна память для каналов общения и систем записи.</span>
        <Link href="#knowledge">
          Как это устроено <ArrowRight size={14} aria-hidden />
        </Link>
      </div>
      <p className="dv15-neural-note">
        {scenario.note} Дополнительные каналы и интеграции уточним под вашу задачу.
      </p>
    </div>
  );
}
