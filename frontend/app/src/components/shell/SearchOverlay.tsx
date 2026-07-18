import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { searchWorkspace } from "@/lib/api";
import type { WorkspaceSearchHit } from "@/lib/types";
import { Dialog } from "@/components/common/Dialog";
import { Input } from "@/components/common/Input";
import { Spinner } from "@/components/common/Feedback";
import s from "./shell.module.css";

/** Cross-conversation semantic search ("find that thing Ben said about
 * chunking"). Same substrate as chat's semantic recall; the server enforces
 * visibility, so private threads that aren't yours can never surface. */
export function SearchOverlay({ wid, onClose }: { wid: string; onClose: () => void }) {
  const nav = useNavigate();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<WorkspaceSearchHit[] | null>(null);
  const [searching, setSearching] = useState(false);

  async function doSearch() {
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    try {
      const r = await searchWorkspace(wid, q);
      setHits(r.items);
    } catch {
      setHits([]);
    } finally { setSearching(false); }
  }

  function open(hit: WorkspaceSearchHit) {
    onClose();
    nav(`/w/${wid}?conv=${hit.conversation_id}&branch=${hit.branch_id}`);
  }

  return (
    <Dialog title="Search the workspace" onClose={onClose}>
      <Input autoFocus placeholder="Search every conversation… (Enter)"
        value={query}
        onChange={(e) => { setQuery(e.target.value); if (hits) setHits(null); }}
        onKeyDown={(e) => e.key === "Enter" && doSearch()} />
      <div style={{ marginTop: 4, minHeight: 40, maxHeight: 380, overflowY: "auto" }}>
        {searching && <Spinner />}
        {!searching && hits === null && (
          <div style={{ fontSize: 12.5, color: "var(--ink-3)", padding: "10px 2px" }}>
            Semantic search over the team's shared threads (and your private ones) —
            phrased ideas match, not just exact words.
          </div>
        )}
        {!searching && hits !== null && hits.length === 0 && (
          <div style={{ fontSize: 13, color: "var(--ink-3)", fontStyle: "italic", padding: "10px 2px" }}>
            Nothing relevant enough — try phrasing it closer to how it was discussed.
          </div>
        )}
        {!searching && hits !== null && hits.map((h) => (
          <button key={h.node_id} className={s.searchHit} onClick={() => open(h)}
            title={`relevance ${h.score.toFixed(2)}`}>
            <div className={s.searchHitHead}>
              <span style={{ color: "var(--oxblood)", fontWeight: 600 }}>{h.conversation_title}</span>
              <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)" }}>
                {h.role === "assistant" ? "⟳ helix" : "✎ teammate"} · {h.score.toFixed(2)}
              </span>
            </div>
            <div className={s.searchHitBody}>{h.excerpt}</div>
          </button>
        ))}
      </div>
    </Dialog>
  );
}
