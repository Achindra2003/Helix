import type { InputHTMLAttributes } from "react";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Input({ label, id, className = "", ...rest }: Props) {
  return (
    <label className="block">
      {label && (
        <span className="mb-1.5 block text-sm font-medium text-muted">
          {label}
        </span>
      )}
      <input
        id={id}
        className={
          "w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm " +
          "text-fg placeholder:text-muted/60 transition " +
          "focus:border-violet/60 focus:outline-none focus:ring-2 focus:ring-violet/30 " +
          className
        }
        {...rest}
      />
    </label>
  );
}
