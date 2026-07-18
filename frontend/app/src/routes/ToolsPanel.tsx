import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getToolSettings, putToolSettings } from "@/lib/api";
import { Button } from "@/components/common/Button";
import { Spinner } from "@/components/common/Feedback";
import { useToast } from "@/components/common/Toast";
import s from "./members.module.css";

/** Owner-governed agent tool allowlist (FR-14). What's checked here is the
 * whole world an agent run's model can see — an un-allowed tool is never
 * offered, not refused. Non-owners see the policy read-only, which is how the
 * composer's Agent button explains itself. */
export function ToolsPanel({ wid, isOwner }: { wid: string; isOwner: boolean }) {
  const qc = useQueryClient();
  const { push } = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ["tool-settings", wid],
    queryFn: () => getToolSettings(wid),
  });

  // Local draft of the allowlist; null until the catalog arrives.
  const [draft, setDraft] = useState<string[] | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (data) setDraft(data.allowed); }, [data]);

  if (isLoading || !data || draft === null) return <Spinner />;

  const dirty = JSON.stringify([...draft].sort()) !== JSON.stringify([...data.allowed].sort());

  function toggle(name: string) {
    setDraft((d) => (d ?? []).includes(name) ? (d ?? []).filter((n) => n !== name) : [...(d ?? []), name]);
  }

  async function save() {
    setSaving(true);
    try {
      await putToolSettings(wid, draft ?? []);
      await qc.invalidateQueries({ queryKey: ["tool-settings", wid] });
      push("Agent tools updated");
    } catch (e: any) {
      push(e?.message ?? "Save failed", "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className={s.matrixHead} style={{ marginTop: 38 }}>
        <span className="serif-d" style={{ fontSize: 22 }}>Agent tools</span>
        <span className={`mono ${s.tag}`}>owner-governed</span>
      </div>
      <div className={s.row} style={{ flexDirection: "column", alignItems: "stretch", gap: 12 }}>
        <div style={{ fontSize: 13, color: "var(--ink-2)" }}>
          Agent runs (the composer's <span className="mono" style={{ fontSize: 12 }}>⚒ Agent</span> button)
          may only use the tools enabled here — anything unchecked is never even offered to the model.
          Tools marked <span style={{ color: "var(--gilt)" }}>⚿</span> leave the workspace, so every call
          pauses for a member's approval first.
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {data.items.map((t) => {
            const on = draft.includes(t.name);
            return (
              <label key={t.name}
                style={{
                  display: "flex", alignItems: "baseline", gap: 10, padding: "9px 12px",
                  borderRadius: 9, border: "1px solid var(--rule-soft)",
                  background: on && t.available ? "var(--paper-3)" : "transparent",
                  opacity: t.available ? 1 : 0.55,
                  cursor: isOwner && t.available ? "pointer" : "default",
                }}>
                {isOwner ? (
                  <input type="checkbox" checked={on} disabled={!t.available || saving}
                    onChange={() => toggle(t.name)} style={{ accentColor: "var(--oxblood)" }} />
                ) : (
                  <span style={{ color: on ? "var(--verde)" : "var(--ink-3)" }}>{on ? "✓" : "·"}</span>
                )}
                <div style={{ minWidth: 0 }}>
                  <span className="mono" style={{ fontSize: 13, color: "var(--ink)" }}>{t.name}</span>
                  {t.sensitive && (
                    <span className="mono" title="Every call pauses for a member's approval"
                      style={{ fontSize: 10.5, color: "var(--gilt)", marginLeft: 8 }}>⚿ needs approval</span>
                  )}
                  {!t.available && (
                    <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-3)", marginLeft: 8 }}>
                      unavailable — this deployment has no key for it
                    </span>
                  )}
                  <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 2 }}>{t.description}</div>
                </div>
              </label>
            );
          })}
        </div>
        {isOwner && (
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <Button variant="primary" disabled={!dirty || saving} onClick={save}>Save tools</Button>
            {dirty && <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-3)" }}>unsaved changes</span>}
            {draft.length === 0 && (
              <span style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
                No tools = agent runs still work, just bare-handed.
              </span>
            )}
          </div>
        )}
      </div>
    </>
  );
}
