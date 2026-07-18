import s from "./common.module.css";

/** Orbital spinner — two counter-rotating rings and a gilt body, the same
 *  astronomical vocabulary as the brand marks (not a generic arc). */
export function Spinner() {
  return (
    <svg viewBox="0 0 36 36" width={26} height={26} role="status" aria-label="loading" className={s.spinner}>
      <g className={s.spinSlow} style={{ transformOrigin: "18px 18px" }}>
        <circle cx="18" cy="18" r="15" fill="none" stroke="var(--rule)" strokeWidth="1.2" strokeDasharray="4 7" />
      </g>
      <g className={s.spinFast} style={{ transformOrigin: "18px 18px" }}>
        <circle cx="18" cy="18" r="9" fill="none" stroke="var(--oxblood)" strokeWidth="1.6" strokeDasharray="35 22" strokeLinecap="round" />
        <circle cx="18" cy="3" r="2.4" fill="var(--gilt-2)" />
      </g>
    </svg>
  );
}

export function EmptyState({ title, children, icon }: { title: string; children?: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className={s.empty}>
      {icon}
      <div className={s.emptyTitle}>{title}</div>
      {children && <div style={{ fontStyle: "italic", lineHeight: 1.55 }}>{children}</div>}
    </div>
  );
}
