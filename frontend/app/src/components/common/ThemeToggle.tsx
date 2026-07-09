import { useEffect, useState } from "react";
import { getTheme, onThemeChange, toggleTheme, type Theme } from "@/lib/theme";
import s from "./common.module.css";

/** Day/night switch: ☾ invites nocturne, ☀ returns to parchment. */
export function ThemeToggle({ floating = false }: { floating?: boolean }) {
  const [theme, setLocal] = useState<Theme>(getTheme());
  useEffect(() => onThemeChange(setLocal), []);
  const dark = theme === "dark";
  return (
    <button
      className={`${s.themeBtn} ${floating ? s.themeBtnFloat : ""}`}
      title={dark ? "Return to daylight parchment" : "Read by candlelight (dark mode)"}
      aria-label="Toggle dark mode"
      onClick={() => toggleTheme()}
    >
      {dark ? "☀" : "☾"}
    </button>
  );
}
