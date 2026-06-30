import { useEffect } from "react";
import s from "./common.module.css";

export function Dialog({
  title, onClose, children, footer,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className={s.scrim} onMouseDown={onClose} role="dialog" aria-modal aria-label={title}>
      <div className={s.dialog} onMouseDown={(e) => e.stopPropagation()}>
        <div className={s.dialogTitle}>{title}</div>
        {children}
        {footer && <div className={s.dialogRow}>{footer}</div>}
      </div>
    </div>
  );
}
