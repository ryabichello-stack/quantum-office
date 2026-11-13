export function DelnoMark({ small = false }: { small?: boolean }) {
  return (
    <span className={small ? "delno-mark mark-small" : "delno-mark"} aria-hidden="true">
      <svg viewBox="0 0 895 847" focusable="false">
        <path d="M0 0h490c266 0 405 184 405 423S756 847 490 847H0V240h101l124 75v357h254c118 0 196-102 196-249 0-123-68-240-208-240H0V0Z" />
      </svg>
    </span>
  );
}
