import { useNavigate, useParams } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { Logo } from "@/components/brand/Logo";
import { useSession } from "@/store/session";
import { initialOf } from "@/lib/format";
import s from "./shell.module.css";

// Labels say what is behind the door, not what we call it in the codebase.
// "LIBR" was a truncation of an internal name — a newcomer had to click it to
// find out it holds saved prompts, which is exactly the tax a horizontal
// product cannot charge.
const NAV = [
  { key: "", glyph: "⌇", label: "CHAT" },
  { key: "map", glyph: "⎇", label: "MAP" },
  { key: "library", glyph: "▦", label: "PROMPTS" },
  { key: "docs", glyph: "⌘", label: "DOCS" },
  { key: "members", glyph: "♔", label: "TEAM" },
];

export function Rail({ active, onSearch }: { active: string; onSearch: () => void }) {
  const nav = useNavigate();
  const { wid } = useParams();
  const reduce = useReducedMotion();
  const user = useSession((st) => st.user);
  return (
    <nav className={s.rail} aria-label="Workspace">
      <button className={s.railLogo} title="Switch workspace" aria-label="Switch workspace"
        onClick={() => nav("/workspaces")}>
        <Logo size={34} />
      </button>
      {NAV.map((n) => {
        const on = active === n.key;
        return (
          <motion.button key={n.key} className={on ? s.navOn : s.navBtn} title={n.label}
            aria-current={on ? "page" : undefined}
            whileTap={{ scale: 0.9 }} transition={{ type: "spring", stiffness: 500, damping: 22 }}
            onClick={() => nav(n.key ? `/w/${wid}/${n.key}` : `/w/${wid}`)}>
            {on && (
              <motion.span layoutId="railActive" className={s.navPill}
                transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 460, damping: 36 }} />
            )}
            {/* The glyph is ornament — hidden so the accessible name is the
                label alone ("TEAM", not "♔ TEAM"). Same treatment the avatar's
                initial already gets. */}
            <span className={s.navGlyph} aria-hidden>{n.glyph}</span>
            <span className={s.navLabel}>{n.label}</span>
          </motion.button>
        );
      })}
      <button className={s.navBtn} title="Search every conversation (Ctrl+K)" onClick={onSearch}>
        <span className={s.navGlyph}>⌕</span>
        <span className={s.navLabel}>FIND</span>
      </button>
      <div className={s.spacer} />
      <button className={s.avatar} title={`${user?.email} — account settings`}
        aria-label={`Account settings for ${user?.email ?? "your account"}`}
        style={{ padding: 0 }} onClick={() => nav("/account")}>
        <span aria-hidden>{initialOf(user?.email)}</span>
      </button>
    </nav>
  );
}
