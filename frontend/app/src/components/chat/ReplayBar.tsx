import s from "./chat.module.css";

// Client-side replay (F9): step through the branch's nodes without any backend —
// the history is already loaded, so we just clamp how many are shown.
export function ReplayBar({
  total, value, onChange,
}: {
  total: number;
  value: number | null; // null = show all (live)
  onChange: (v: number | null) => void;
}) {
  const active = value !== null;
  const shown = value ?? total;
  return (
    <div className={s.chip} style={{ gap: 8, padding: "4px 8px" }} title="Replay the thread step by step">
      <button
        style={{ background: "none", border: "none", color: active ? "var(--oxblood)" : "var(--ink-3)", fontSize: 12 }}
        onClick={() => onChange(active ? null : 1)}
      >
        {active ? "● replay" : "▷ replay"}
      </button>
      {active && (
        <>
          <input
            type="range" min={1} max={total} value={shown}
            onChange={(e) => onChange(Number(e.target.value))}
            style={{ width: 90 }}
          />
          <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>{shown}/{total}</span>
        </>
      )}
    </div>
  );
}
