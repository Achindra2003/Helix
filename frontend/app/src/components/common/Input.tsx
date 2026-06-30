import type { InputHTMLAttributes } from "react";
import s from "./common.module.css";

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className={s.field}>
      <span className="eyebrow">{label}</span>
      {children}
    </label>
  );
}

export function Input({ className = "", ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`${s.input} ${className}`} {...rest} />;
}
