import s from "./common.module.css";

export function Spinner() {
  return <div className={s.spinner} aria-label="loading" role="status" />;
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
