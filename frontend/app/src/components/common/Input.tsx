import type { InputHTMLAttributes, SelectHTMLAttributes } from "react";
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

/**
 * A select whose caret we draw ourselves.
 *
 * The native control paints its arrow hard against its own right edge, inside
 * whatever padding you give it — so the arrow sat a few pixels from the border
 * with the label crowding it from the other side, and no amount of
 * `padding-right` moved it. There is also no way to make the OS arrow take the
 * page's ink colour, so in Nocturne it stayed a light-theme grey.
 *
 * So: `appearance: none`, and the caret becomes a mark on the wrapper, inset
 * from the edge by the same amount as the text. A select now has the same
 * internal margins as every other control on the page, in both themes.
 */
export function Select({
  className = "", compact = false, children, ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & {
  /** Inline in a row beside other small controls, rather than filling a field.
   *  Field-sized is the default so a select sitting next to an Input matches
   *  it — they were two different heights in the provider form. */
  compact?: boolean;
}) {
  return (
    <span className={`${s.selectWrap} ${compact ? s.selectWrapCompact : ""}`}>
      <select className={`${s.select} ${compact ? s.selectCompact : ""} ${className}`} {...rest}>
        {children}
      </select>
      <span className={s.selectCaret} aria-hidden>⌄</span>
    </span>
  );
}
