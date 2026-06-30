import type { ButtonHTMLAttributes } from "react";
import s from "./common.module.css";

type Variant = "default" | "primary" | "gilt" | "oxblood" | "ghost";

const VARIANT_CLASS: Record<Variant, string> = {
  default: "",
  primary: s.primary,
  gilt: s.gilt,
  oxblood: s.oxblood,
  ghost: s.ghost,
};

export function Button({
  variant = "default",
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return <button className={`${s.btn} ${VARIANT_CLASS[variant]} ${className}`} {...rest} />;
}
