import { useNavigate, useParams } from "react-router-dom";
import { Logo } from "@/components/brand/Logo";
import { useSession } from "@/store/session";
import { initialOf } from "@/lib/format";
import s from "./shell.module.css";

const NAV = [
  { key: "", glyph: "⌇", label: "CHAT" },
  { key: "map", glyph: "⎇", label: "MAP" },
  { key: "library", glyph: "▦", label: "LIBR" },
  { key: "docs", glyph: "⌘", label: "DOCS" },
  { key: "members", glyph: "♔", label: "TEAM" },
];

export function Rail({ active }: { active: string }) {
  const nav = useNavigate();
  const { wid } = useParams();
  const user = useSession((st) => st.user);
  return (
    <div className={s.rail}>
      <button className={s.railLogo} title="Switch workspace" onClick={() => nav("/workspaces")}>
        <Logo size={34} />
      </button>
      {NAV.map((n) => {
        const on = active === n.key;
        return (
          <button key={n.key} className={on ? s.navOn : s.navBtn} title={n.label}
            onClick={() => nav(n.key ? `/w/${wid}/${n.key}` : `/w/${wid}`)}>
            <span className={s.navGlyph}>{n.glyph}</span>
            <span className={s.navLabel}>{n.label}</span>
          </button>
        );
      })}
      <div className={s.spacer} />
      <div className={s.avatar} title={user?.email}>{initialOf(user?.email)}</div>
    </div>
  );
}
