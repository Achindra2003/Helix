// The Map (Phase 1 of ui-standout): the team's reasoning as a place.
//
// Every conversation renders as a stemma — its main spine of turns laid
// vertically, forks splitting into their own columns at the exact node they
// diverged — with references drawn as gilt threads between conversation
// cartouches and live presence dots on the branches teammates have open now.
// Click any node to land in that thread on that branch.
//
// Layout is deterministic (no graph library): columns by DFS over the branch
// tree, rows by node seq, conversations flowing left→right. Node payloads are
// lean (no content); hover fetches the branch history lazily for an excerpt.
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getWorkspaceMap, getHistory } from "@/lib/api";
import { onRoomEvent } from "@/lib/realtime";
import { usePresenceStore } from "@/store/presence";
import { useSession } from "@/store/session";
import type { MapConversation, MapNode, Node } from "@/lib/types";
import { colorFor } from "@/lib/format";
import { Frontispiece } from "@/components/brand/Frontispiece";
import s from "./map.module.css";

// --- deterministic stemma layout ------------------------------------------

const COLW = 36;   // px between branch columns
const ROWH = 30;   // px between turns on a spine
const PAD = 26;    // inner padding of a conversation block
const TITLE_H = 52; // cartouche height incl. gap to first node
const GAP = 84;    // gap between conversation blocks
const R = 5.5;     // node radius

interface LaidNode {
  node: MapNode;
  convId: string;
  x: number;
  y: number;
  forkPoint: boolean;
}

interface LaidBranch {
  id: string;
  name: string;
  convId: string;
  x: number;       // column x
  yFirst: number;  // y of its first own node (or ghost)
  yLast: number;
  ghost: boolean;  // forked but no own turns yet
}

interface LaidConv {
  conv: MapConversation;
  x: number;
  w: number;
  h: number;
}

interface Layout {
  convs: LaidConv[];
  nodes: LaidNode[];
  branches: LaidBranch[];
  spines: string[];    // svg paths, plain ink
  forkEdges: string[]; // fork node -> child branch first node
  refEdges: string[];  // conversation -> conversation, gilt
  width: number;
  height: number;
}

function layoutWorkspace(conversations: MapConversation[]): Layout {
  const convs: LaidConv[] = [];
  const nodes: LaidNode[] = [];
  const branches: LaidBranch[] = [];
  const spines: string[] = [];
  const forkEdges: string[] = [];
  let xCursor = 0;
  let maxH = 0;

  for (const conv of conversations) {
    const byBranch = new Map<string, MapNode[]>();
    for (const n of conv.nodes) {
      const arr = byBranch.get(n.branch_id) ?? [];
      arr.push(n);
      byBranch.set(n.branch_id, arr);
    }
    byBranch.forEach((arr) => arr.sort((a, b) => a.seq - b.seq));

    const children = new Map<string | null, typeof conv.branches>();
    for (const b of conv.branches) {
      const arr = children.get(b.parent_branch_id) ?? [];
      arr.push(b);
      children.set(b.parent_branch_id, arr);
    }
    const root =
      conv.branches.find((b) => b.parent_branch_id === null) ?? conv.branches[0];

    // DFS: parent before child, each branch takes the next free column.
    const col = new Map<string, number>();
    const order: typeof conv.branches = [];
    let nextCol = 0;
    const visit = (b: (typeof conv.branches)[number]) => {
      col.set(b.id, nextCol++);
      order.push(b);
      for (const c of children.get(b.id) ?? []) visit(c);
    };
    if (root) visit(root);

    const rowOf = new Map<string, number>(); // node id -> row
    const convNodes: LaidNode[] = [];
    const forkIds = new Set(
      conv.branches.map((b) => b.fork_node_id).filter(Boolean) as string[],
    );
    let maxRow = 0;

    for (const b of order) {
      const own = byBranch.get(b.id) ?? [];
      // A fork's rows continue below its fork point (parent laid first, so
      // the fork node's row is known); the root starts at the top.
      const startRow =
        b.fork_node_id != null ? (rowOf.get(b.fork_node_id) ?? -1) + 1 : 0;
      own.forEach((n, i) => rowOf.set(n.id, startRow + i));

      const cx = xCursor + PAD + (col.get(b.id) ?? 0) * COLW;
      const ys = own.map((n) => TITLE_H + (rowOf.get(n.id) ?? 0) * ROWH);
      for (let i = 0; i < own.length; i++) {
        convNodes.push({
          node: own[i],
          convId: conv.id,
          x: cx,
          y: ys[i],
          forkPoint: forkIds.has(own[i].id),
        });
        maxRow = Math.max(maxRow, rowOf.get(own[i].id) ?? 0);
      }
      if (ys.length > 1) {
        spines.push(`M ${cx} ${ys[0]} L ${cx} ${ys[ys.length - 1]}`);
      }

      const ghost = own.length === 0 && b.fork_node_id != null;
      const ghostRow =
        b.fork_node_id != null ? (rowOf.get(b.fork_node_id) ?? 0) + 1 : 0;
      const yFirst = ys[0] ?? TITLE_H + ghostRow * ROWH;
      const yLast = ys[ys.length - 1] ?? yFirst;
      if (ghost) maxRow = Math.max(maxRow, ghostRow);
      branches.push({
        id: b.id,
        name: b.name,
        convId: conv.id,
        x: cx,
        yFirst,
        yLast,
        ghost,
      });

      // Fork edge: from the divergence node over to this branch's first turn.
      if (b.fork_node_id != null) {
        const from = convNodes.find((n) => n.node.id === b.fork_node_id);
        if (from) {
          const midY = (from.y + yFirst) / 2;
          forkEdges.push(
            `M ${from.x} ${from.y} C ${from.x} ${midY}, ${cx} ${midY}, ${cx} ${yFirst}`,
          );
        }
      }
    }

    const nCols = Math.max(nextCol, 1);
    const w = Math.max(PAD * 2 + (nCols - 1) * COLW, 168);
    const h = TITLE_H + (maxRow + 1) * ROWH + PAD;
    convs.push({ conv, x: xCursor, w, h });
    nodes.push(...convNodes);
    maxH = Math.max(maxH, h);
    xCursor += w + GAP;
  }

  // Reference threads between cartouches, drawn as arcs above the blocks.
  const refEdges: string[] = [];
  const byId = new Map(convs.map((c) => [c.conv.id, c]));
  for (const c of convs) {
    for (const target of c.conv.references) {
      const t = byId.get(target);
      if (!t) continue; // target may be private-to-someone-else
      const x1 = c.x + c.w / 2;
      const x2 = t.x + t.w / 2;
      const lift = 34 + Math.min(60, Math.abs(x2 - x1) / 8);
      refEdges.push(`M ${x1} 10 C ${x1} ${10 - lift}, ${x2} ${10 - lift}, ${x2} 10`);
    }
  }

  return {
    convs,
    nodes,
    branches,
    spines,
    forkEdges,
    refEdges,
    width: Math.max(xCursor - GAP, 1),
    height: Math.max(maxH, 1),
  };
}

// --- the view ---------------------------------------------------------------

interface Hover {
  node: MapNode;
  sx: number; // screen coords for the floating card
  sy: number;
  excerpt: string | null;
}

export function MapView() {
  const { wid } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const user = useSession((st) => st.user);
  const presence = usePresenceStore((st) => st.users);

  const { data } = useQuery({
    queryKey: ["map", wid],
    queryFn: () => getWorkspaceMap(wid!),
    enabled: !!wid,
  });
  const conversations = data?.conversations ?? [];
  const layout = useMemo(() => layoutWorkspace(conversations), [conversations]);

  // Live: structural room events refresh the map in place.
  useEffect(
    () =>
      onRoomEvent((ev) => {
        if (
          ev.kind === "conversation.created" ||
          ev.kind === "branch.created" ||
          ev.kind === "references.updated" ||
          (ev.kind === "run_event" && ev.event?.kind === "done")
        ) {
          qc.invalidateQueries({ queryKey: ["map", wid] });
        }
      }),
    [wid, qc],
  );

  // Pan/zoom: translate+scale on an svg group; wheel zooms around the cursor.
  const canvasRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ x: 60, y: 80, k: 1 });
  const fitted = useRef(false);
  const drag = useRef<{ px: number; py: number; vx: number; vy: number } | null>(null);

  function fit() {
    if (!layout.convs.length || !canvasRef.current) return;
    const box = canvasRef.current.getBoundingClientRect();
    const k = Math.min(
      1,
      (box.width - 120) / layout.width,
      (box.height - 160) / (layout.height + 80),
      1.4,
    );
    setView({
      x: (box.width - layout.width * k) / 2,
      y: 90 * k + Math.max(0, (box.height - (layout.height + 90) * k) / 2),
      k: Math.max(k, 0.35),
    });
  }

  useEffect(() => {
    // Fit-and-center once when real content first arrives.
    if (fitted.current || !layout.convs.length || !canvasRef.current) return;
    fit();
    fitted.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout]);

  /** Zoom around a screen point (cursor, or the canvas center for buttons). */
  function zoomAt(mx: number, my: number, factor: number) {
    setView((v) => {
      const k = Math.min(2.5, Math.max(0.35, v.k * factor));
      // keep the point under the cursor fixed while scaling
      return { k, x: mx - ((mx - v.x) / v.k) * k, y: my - ((my - v.y) / v.k) * k };
    });
  }
  function onWheel(e: React.WheelEvent) {
    const box = canvasRef.current!.getBoundingClientRect();
    zoomAt(e.clientX - box.left, e.clientY - box.top, Math.exp(-e.deltaY * 0.0012));
  }
  function zoomCenter(factor: number) {
    const box = canvasRef.current?.getBoundingClientRect();
    if (box) zoomAt(box.width / 2, box.height / 2, factor);
  }
  function onPointerDown(e: React.PointerEvent) {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    drag.current = { px: e.clientX, py: e.clientY, vx: view.x, vy: view.y };
  }
  function onPointerMove(e: React.PointerEvent) {
    if (!drag.current) return;
    const d = drag.current;
    setView((v) => ({ ...v, x: d.vx + e.clientX - d.px, y: d.vy + e.clientY - d.py }));
  }
  function onPointerUp() { drag.current = null; }

  // Hover excerpts: history per branch, fetched once and cached.
  const histCache = useRef<Map<string, Promise<Node[]>>>(new Map());
  const [hover, setHover] = useState<Hover | null>(null);
  function onNodeEnter(n: MapNode, e: React.MouseEvent) {
    setHover({ node: n, sx: e.clientX + 14, sy: e.clientY + 12, excerpt: null });
    let p = histCache.current.get(n.branch_id);
    if (!p) {
      p = getHistory(n.branch_id).then((r) => r.nodes);
      histCache.current.set(n.branch_id, p);
    }
    p.then((nodes) => {
      const full = nodes.find((x) => x.id === n.id);
      setHover((h) =>
        h && h.node.id === n.id ? { ...h, excerpt: full?.content ?? "(unavailable)" } : h,
      );
    }).catch(() => {});
  }

  function openBranch(convId: string, branchId: string) {
    nav(`/w/${wid}?conv=${convId}&branch=${branchId}`);
  }

  // Presence dots: teammates (not me) on the branches they're viewing.
  const viewingDots = useMemo(() => {
    const perBranch = new Map<string, { email: string }[]>();
    for (const u of presence) {
      if (!u.viewing || u.user_id === user?.id) continue;
      const arr = perBranch.get(u.viewing) ?? [];
      arr.push({ email: u.email });
      perBranch.set(u.viewing, arr);
    }
    const dots: { x: number; y: number; email: string }[] = [];
    for (const b of layout.branches) {
      const here = perBranch.get(b.id);
      if (!here) continue;
      here.forEach((u, i) => dots.push({ x: b.x + 14 + i * 12, y: b.yLast, email: u.email }));
    }
    return dots;
  }, [presence, layout, user?.id]);

  const isEmpty = conversations.length === 0;

  return (
    <div className={`${s.wrap} folio`}>
      <div className={s.toolbar}>
        <div className={s.title}>The Map</div>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
          drag to pan · scroll to zoom · click a node to enter
        </span>
        <div className={s.legend}>
          <span><svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="var(--ink-2)" /></svg> you ask</span>
          <span><svg width="12" height="12"><circle cx="6" cy="6" r="4.5" fill="var(--paper)" stroke="var(--ink-2)" strokeWidth="1.5" /></svg> Helix answers</span>
          <span><svg width="14" height="12"><circle cx="7" cy="6" r="4.5" fill="none" stroke="var(--oxblood)" strokeWidth="1.5" /></svg> fork point</span>
          <span><svg width="22" height="12"><path d="M 2 6 L 20 6" stroke="var(--gilt)" strokeWidth="1.5" strokeDasharray="4 4" /></svg> reference</span>
          <span><svg width="12" height="12" className={s.presenceDot}><circle cx="6" cy="6" r="4" fill="var(--verde)" /></svg> teammate here</span>
        </div>
      </div>

      {isEmpty ? (
        <div className={s.empty}>
          <div>
            <Frontispiece size={280} animate={false} />
            <div style={{ fontFamily: "var(--font-display)", fontSize: 18, marginTop: 18, color: "var(--ink)" }}>
              An unmarked page
            </div>
            <div style={{ fontSize: 14, color: "var(--ink-3)", marginTop: 8, maxWidth: 380 }}>
              Start a conversation, fork it where the team diverges, and the map
              begins to draw itself.
            </div>
          </div>
        </div>
      ) : (
        <div
          className={s.canvas}
          ref={canvasRef}
          onWheel={onWheel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={() => { onPointerUp(); setHover(null); }}
        >
          <svg className={s.svg}>
            <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
              {/* gilt reference threads first, behind everything */}
              {layout.refEdges.map((d, i) => (
                <path key={`ref-${i}`} className={s.refEdge} d={d} />
              ))}

              {layout.convs.map(({ conv, x, w }) => (
                <g key={conv.id} transform={`translate(${x} 0)`}>
                  <g
                    className={s.cartouche}
                    onClick={() => openBranch(conv.id, conv.default_branch_id)}
                  >
                    <rect className={s.cartoucheBox} x={-10} y={-2} width={w + 20} height={30} rx={7} />
                    <text className={s.cartoucheText} x={w / 2} y={17} textAnchor="middle">
                      {conv.visibility === "private" ? "◍ " : "⊙ "}
                      {conv.title.length > 24 ? conv.title.slice(0, 23) + "…" : conv.title}
                    </text>
                  </g>
                </g>
              ))}

              {layout.spines.map((d, i) => (
                <path key={`sp-${i}`} className={s.spine} d={d} />
              ))}
              {layout.forkEdges.map((d, i) => (
                <path key={`fk-${i}`} className={s.forkEdge} d={d} />
              ))}

              {/* branch name labels + ghost stubs for empty forks */}
              {layout.branches.map((b) =>
                b.name === "main" && !b.ghost ? null : (
                  <g key={`bl-${b.id}`}>
                    {b.ghost && (
                      <circle
                        cx={b.x} cy={b.yFirst} r={R - 1.5}
                        fill="none" stroke="var(--ink-faint)" strokeWidth={1.2} strokeDasharray="2.5 2.5"
                        style={{ cursor: "pointer" }}
                        onClick={() => openBranch(b.convId, b.id)}
                      />
                    )}
                    <text className={s.branchLabel} x={b.x + 9} y={b.yFirst + 3.5}>
                      ⎇ {b.name}
                    </text>
                  </g>
                ),
              )}

              {layout.nodes.map((ln) => (
                <g key={ln.node.id}>
                  {ln.forkPoint && (
                    <circle cx={ln.x} cy={ln.y} r={R + 3.5} fill="none" stroke="var(--oxblood)" strokeWidth={1.4} />
                  )}
                  <circle
                    className={s.node}
                    cx={ln.x} cy={ln.y} r={R}
                    fill={ln.node.role === "user" ? "var(--ink-2)" : "var(--paper)"}
                    stroke="var(--ink-2)" strokeWidth={1.5}
                    onClick={() => openBranch(ln.convId, ln.node.branch_id)}
                    onMouseEnter={(e) => onNodeEnter(ln.node, e)}
                    onMouseLeave={() => setHover(null)}
                  />
                </g>
              ))}

              {viewingDots.map((d, i) => (
                <circle
                  key={`pd-${i}`}
                  className={s.presenceDot}
                  cx={d.x} cy={d.y} r={4.5}
                  fill={colorFor(d.email)} stroke="var(--paper)" strokeWidth={1.5}
                >
                  <title>{d.email} is reading here</title>
                </circle>
              ))}
            </g>
          </svg>

          <div className={s.zoomCtl}>
            <button onClick={() => zoomCenter(1.3)} title="Zoom in">＋</button>
            <button onClick={() => zoomCenter(1 / 1.3)} title="Zoom out">−</button>
            <button onClick={fit} title="Fit the whole map">◱</button>
          </div>

          {hover && (
            <div className={s.hoverCard} style={{ left: hover.sx, top: hover.sy }}>
              <div className={s.hoverRole}>
                {hover.node.role === "user" ? "✒ a teammate asked" : "❧ Helix answered"}
              </div>
              <div className={s.hoverBody}>
                {hover.excerpt === null ? "…" : hover.excerpt || "(empty)"}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
