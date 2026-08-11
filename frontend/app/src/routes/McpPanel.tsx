import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listMcpServers, addMcpServer, syncMcpServer, reviewMcpTool, removeMcpServer,
} from "@/lib/api";
import type { McpServer } from "@/lib/types";
import { Button } from "@/components/common/Button";
import { Dialog } from "@/components/common/Dialog";
import { Input, Field } from "@/components/common/Input";
import { Spinner } from "@/components/common/Feedback";
import { useToast } from "@/components/common/Toast";
import { STATE } from "@/lib/glyphs";
import s from "./members.module.css";

/** MCP servers — where the workspace's agent gets tools we did not write.
 *
 * The panel's job is not "manage servers". It is to make one thing impossible
 * to miss: a tool description is text a third party wrote that goes straight
 * into the model's context, and approving a tool means approving that text. So
 * descriptions are shown verbatim and in full, and a description that changed
 * since it was read is flagged loudly rather than quietly re-approved.
 */
export function McpPanel({ wid, isOwner }: { wid: string; isOwner: boolean }) {
  const qc = useQueryClient();
  const { push } = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ["mcp", wid],
    queryFn: () => listMcpServers(wid),
  });
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const servers = data?.items ?? [];
  const drifted = servers.flatMap((sv) => sv.tools.filter((t) => t.needs_review));

  async function act<T>(key: string, run: () => Promise<T>, ok?: (r: T) => string) {
    setBusy(key);
    try {
      const r = await run();
      await qc.invalidateQueries({ queryKey: ["mcp", wid] });
      await qc.invalidateQueries({ queryKey: ["tool-settings", wid] });
      if (ok) push(ok(r));
    } catch (e: any) {
      push(e?.message ?? "That didn't work", "error");
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) return <Spinner />;

  return (
    <>
      <div className={s.matrixHead} style={{ marginTop: 38 }}>
        <span className="serif-d" style={{ fontSize: 22 }}>Tool servers (MCP)</span>
        <span className={`mono ${s.tag}`}>owner-governed</span>
      </div>

      <div className={s.row} style={{ flexDirection: "column", alignItems: "stretch", gap: 14 }}>
        <div style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.6 }}>
          An MCP server lets this workspace's agent use tools we did not write — a
          GitHub server, an internal service, anything speaking the protocol.
          Discovered tools join the same catalog above and obey the same allowlist,
          and they arrive marked <span style={{ color: "var(--gilt)" }} aria-hidden>{STATE.waiting}</span>{" "}
          <em>needs approval</em> by default, because a remote server is outside this
          workspace by definition.
        </div>

        {drifted.length > 0 && (
          // The one thing worth interrupting someone about. A server that can
          // rewrite a description after approval could tell the model anything.
          <div style={{
            fontSize: 12, lineHeight: 1.55, padding: "10px 12px", borderRadius: 9,
            border: "1px solid var(--oxblood)", color: "var(--ink-2)",
            background: "rgba(143, 62, 19, 0.08)",
          }}>
            <strong style={{ color: "var(--oxblood)" }}>
              {drifted.length} tool{drifted.length > 1 ? "s" : ""} changed since{" "}
              {drifted.length > 1 ? "they were" : "it was"} reviewed.
            </strong>{" "}
            The server has rewritten what the model will be told. Read the new text
            below and accept it, or leave it — until then those tools are not offered
            to the model at all.
          </div>
        )}

        {servers.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--ink-3)" }}>
            No tool servers. Agent runs use the built-in tools above.
          </div>
        ) : (
          servers.map((sv) => (
            <ServerCard
              key={sv.id} server={sv} isOwner={isOwner} busy={busy === sv.id}
              onSync={() => act(sv.id, () => syncMcpServer(wid, sv.id), (r) =>
                r.summary.needs_review > 0
                  ? `${r.summary.discovered} tools · ${r.summary.needs_review} changed and need re-reading`
                  : `${r.summary.discovered} tools, nothing changed`)}
              onRemove={() => act(sv.id, () => removeMcpServer(wid, sv.id), () => `${sv.name} removed`)}
              onReview={(tool) => act(sv.id, () => reviewMcpTool(wid, sv.id, tool), () => `${tool} accepted as read`)}
            />
          ))
        )}

        {isOwner && (
          <div>
            <Button onClick={() => setAdding(true)}>+ Add a server</Button>
          </div>
        )}
      </div>

      {adding && (
        <AddServerDialog
          onClose={() => setAdding(false)}
          onSubmit={async (body) => {
            await act("new", () => addMcpServer(wid, body), () => "Server added");
            setAdding(false);
          }}
        />
      )}
    </>
  );
}

function ServerCard({ server, isOwner, busy, onSync, onRemove, onReview }: {
  server: McpServer;
  isOwner: boolean;
  busy: boolean;
  onSync: () => void;
  onRemove: () => void;
  onReview: (tool: string) => void;
}) {
  return (
    <div style={{
      border: "1px solid var(--rule-soft)", borderRadius: 9, padding: "12px 14px",
      display: "flex", flexDirection: "column", gap: 10,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span className="mono" style={{ fontSize: 13, color: "var(--ink)" }}>{server.name}</span>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)", minWidth: 0, overflowWrap: "anywhere" }}>
          {server.url}
        </span>
        {server.has_auth && (
          <span className="mono" style={{ fontSize: 10, color: "var(--ink-3)" }}>
            {server.auth_header || "authenticated"}
          </span>
        )}
        <div style={{ flex: 1 }} />
        {isOwner && (
          <>
            <Button variant="ghost" disabled={busy} onClick={onSync}
              style={{ padding: "4px 10px", fontSize: 12 }}
              title="Ask the server what it offers now">refresh</Button>
            <Button variant="ghost" disabled={busy} onClick={onRemove}
              style={{ padding: "4px 10px", fontSize: 12, color: "var(--oxblood)" }}>remove</Button>
          </>
        )}
      </div>

      {server.last_error && (
        <div className="mono" style={{ fontSize: 11, color: "var(--oxblood)", overflowWrap: "anywhere" }}>
          {server.last_error}
        </div>
      )}

      {server.tools.length === 0 ? (
        <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
          {server.last_error ? "No tools — the last refresh failed." : "This server offered no tools."}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {server.tools.map((t) => (
            <div key={t.name} style={{
              paddingLeft: 10,
              borderLeft: `2px solid ${t.needs_review ? "var(--oxblood)" : "var(--rule-soft)"}`,
            }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span className="mono" style={{ fontSize: 12, color: "var(--ink)" }}>{t.name}</span>
                {t.sensitive && (
                  <span className="mono" style={{ fontSize: 10, color: "var(--gilt)" }}>
                    {STATE.waiting} needs approval
                  </span>
                )}
                {t.needs_review && (
                  <span className="mono" style={{ fontSize: 10, color: "var(--oxblood)" }}>
                    description changed — not offered to the model
                  </span>
                )}
              </div>
              {/* Verbatim and in full. Truncating this would hide exactly the
                  sentence a prompt injection would be hiding in. */}
              <div style={{
                fontSize: 12, color: "var(--ink-3)", marginTop: 3, lineHeight: 1.5,
                whiteSpace: "pre-wrap", overflowWrap: "anywhere",
              }}>
                {t.description || <em>no description</em>}
              </div>
              {t.needs_review && isOwner && (
                <Button variant="ghost" disabled={busy} onClick={() => onReview(t.name)}
                  style={{ padding: "3px 9px", fontSize: 11, marginTop: 6 }}>
                  I've read this — accept it
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AddServerDialog({ onClose, onSubmit }: {
  onClose: () => void;
  onSubmit: (body: { name: string; url: string; auth_header?: string; auth_value?: string }) => void;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [header, setHeader] = useState("Authorization");
  const [value, setValue] = useState("");
  const ready = name.trim() && url.trim();

  return (
    <Dialog title="Add a tool server" onClose={onClose}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={!ready}
          onClick={() => onSubmit({
            name: name.trim(), url: url.trim(),
            auth_header: value.trim() ? header.trim() : "",
            auth_value: value.trim(),
          })}>Add and discover</Button>
      </>}>
      <Field label="Name — how its tools are attributed in the record">
        <Input value={name} autoFocus onChange={(e) => setName(e.target.value)} placeholder="github" />
      </Field>
      <Field label="Server URL">
        <Input value={url} onChange={(e) => setUrl(e.target.value)}
          placeholder="https://api.githubcopilot.com/mcp/" />
      </Field>
      <Field label="Auth header (leave the value empty for an open server)">
        <Input value={header} onChange={(e) => setHeader(e.target.value)} placeholder="Authorization" />
      </Field>
      <Field label="Auth value — encrypted at rest, never shown again">
        <Input type="password" value={value} onChange={(e) => setValue(e.target.value)}
          placeholder="Bearer ghp_…" />
      </Field>
      <div style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.55 }}>
        Its tools are discovered immediately but not permitted: you still choose
        each one in <strong>Agent tools</strong> above, after reading what the
        server says it does.
      </div>
    </Dialog>
  );
}
