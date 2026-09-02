"use client";

import { orbAssetPath } from "@/lib/delnoVoice";
import type { VoicePhase } from "@/lib/delnoVoice";

type CrystalOrbProps = {
  variant?: "widget" | "demo";
  voiceActive: boolean;
  voicePhase: VoicePhase;
  onOrbClick: () => void;
  showChatButton?: boolean;
  onChatClick?: () => void;
};

export function CrystalOrb({
  variant = "widget",
  voiceActive,
  voicePhase,
  onOrbClick,
  showChatButton = false,
  onChatClick,
}: CrystalOrbProps) {
  const orbSrc = orbAssetPath();

  return (
    <div className={`widget widget-${variant}`}>
      <div className="state">
        <span className="listen">Слушаю…</span>
        <span className="think">Думаю…</span>
        <span className="speak">Отвечаю…</span>
      </div>

      {showChatButton ? (
        <button type="button" className="chat" aria-label="Текстовый чат" onClick={onChatClick}>
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" aria-hidden>
            <path
              d="M5.5 6.2h13a2.3 2.3 0 0 1 2.3 2.3v6.2a2.3 2.3 0 0 1-2.3 2.3H11l-4.5 2.8V17H5.5a2.3 2.3 0 0 1-2.3-2.3V8.5a2.3 2.3 0 0 1 2.3-2.3Z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      ) : null}

      <div className="orb-anchor">
        <button
          type="button"
          className="orb-hit"
          aria-label={voiceActive ? "Остановить голосовой режим" : "Говорить с DELNO"}
          aria-pressed={voiceActive}
          onClick={onOrbClick}
        />

        <div className={`motion${voicePhase !== "idle" && voicePhase !== "error" ? " is-live" : ""}`}>
          <span className="ground" />

          <div className="rings" aria-hidden="true">
            <i className="sharp r1" />
            <i className="soft r2" />
            <i className="sharp r3" />
          </div>

          <span className="active-halo" />

          <div className="breath">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="orb-img" src={orbSrc} alt="" />
            <span className="fire-path">
              <span className="fire fire-idle" />
              <span className="fire fire-active" />
            </span>
          </div>

          <span className="icon mic">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" aria-hidden>
              <path
                d="M12 15.1a3.6 3.6 0 0 0 3.6-3.6V7.2a3.6 3.6 0 1 0-7.2 0v4.3a3.6 3.6 0 0 0 3.6 3.6Z"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
              <path
                d="M6.8 11.3a5.2 5.2 0 0 0 10.4 0M12 16.5v3M9.5 19.5h5"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              />
            </svg>
          </span>

          <span className="icon dots">
            <i />
            <i />
            <i />
          </span>
          <span className="icon wave">
            <i />
            <i />
            <i />
            <i />
            <i />
          </span>
        </div>
      </div>
    </div>
  );
}
