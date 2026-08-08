import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getProviderSettings, putProviderSettings, testProviderSettings, getWorkspaceUsage,
} from "@/lib/api";
import { Button } from "@/components/common/Button";
import { Field, Input } from "@/components/common/Input";
import { Spinner } from "@/components/common/Feedback";
import { useToast } from "@/components/common/Toast";
import s from "./members.module.css";

const PROVIDERS = [
  { value: "", label: "Server default (inherit)" },
  { value: "groq", label: "Groq — hosted, needs an API key" },
  { value: "openai_compatible", label: "OpenAI-compatible endpoint (vLLM, OpenRouter…)" },
  { value: "ollama", label: "Ollama — for self-hosted Helix" },
];

/** Where this workspace's thinking actually happens.
 *
 * The privacy posture is the strongest reason a research group would choose
 * Helix, and the panel used to express it only as an entry in a dropdown. A
 * team evaluating whether their unpublished work can go in here should not have
 * to infer the answer from the word "Ollama". */
const POSTURE: Record<string, string> = {
  "": "Follows whatever this server is configured to use. Ask whoever runs the instance where that is.",
  groq: "Messages are sent to Groq's API, billed to this workspace's own key.",
  openai_compatible: "Messages are sent to the endpoint you name below — your own vLLM box, a router, anything OpenAI-shaped.",
  ollama: "Nothing leaves the machine running Helix. Conversations, documents and reasoning runs all stay local.",
};

/** Owner-editable per-workspace LLM provider (BYO key). Non-owners see the
 * effective status only — enough to know why the composer is (or isn't) alive. */
export function ProviderPanel({ wid, isOwner }: { wid: string; isOwner: boolean }) {
  const qc = useQueryClient();
  const { push } = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ["provider-settings", wid],
    queryFn: () => getProviderSettings(wid),
  });
  // Lifetime spend on this workspace's own key. Chat is an approximation
  // (streamed chunk count); deep-run tokens are the measured number.
  const { data: usage } = useQuery({
    queryKey: ["workspace-usage", wid],
    queryFn: () => getWorkspaceUsage(wid),
  });

  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState(""); // only sent when non-empty (write-only field)
  const [baseUrl, setBaseUrl] = useState("");
  const [chatModel, setChatModel] = useState("");
  const [deepModel, setDeepModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; detail: string } | null>(null);

  useEffect(() => {
    if (!data) return;
    setProvider(data.provider);
    setBaseUrl(data.base_url ?? "");
    setChatModel(data.chat_model);
    setDeepModel(data.deep_model);
  }, [data]);

  async function save(clearKey = false): Promise<boolean> {
    setSaving(true);
    setTestResult(null);
    try {
      await putProviderSettings(wid, {
        provider,
        // Omitted = keep the stored key; "" = clear it; text = replace it.
        api_key: clearKey ? "" : apiKey.trim() ? apiKey.trim() : undefined,
        base_url: baseUrl.trim(),
        chat_model: chatModel.trim(),
        deep_model: deepModel.trim(),
      });
      setApiKey("");
      await qc.invalidateQueries({ queryKey: ["provider-settings", wid] });
      push(clearKey ? "Key removed" : "Provider settings saved");
      return true;
    } catch (e: any) {
      push(e?.message ?? "Save failed", "error");
      return false;
    } finally {
      setSaving(false);
    }
  }

  // Test first, save only if it answered. This used to save and then test,
  // which meant a typo'd key became the workspace's live configuration and
  // every message failed until someone noticed — the panel would cheerfully
  // report the connection was broken *after* breaking it.
  async function testAndSave() {
    setSaving(true);
    setTestResult(null);
    let result: { ok: boolean; detail: string };
    try {
      result = await testProviderSettings(wid, {
        provider,
        // Omitted = test the stored key, so changing only a model doesn't
        // require re-pasting a key the owner cannot read back.
        api_key: apiKey.trim() || undefined,
        base_url: baseUrl.trim(),
        chat_model: chatModel.trim(),
        deep_model: deepModel.trim(),
      });
    } catch (e: any) {
      result = { ok: false, detail: e?.message ?? "Test failed" };
    }
    setTestResult(result);
    setSaving(false);
    if (result.ok) await save();
    else push("Not saved — the provider did not answer", "error");
  }

  if (isLoading || !data) return <Spinner />;

  // A labelled table, not a run-on line. This was six unlabelled facts in a
  // single wrapping row — "ready chat: groq / llama-3.1-8b-instant deep:
  // llama-3.3-70b-versatile server default spend: 2,302 in · 48 out · ~$0.0001"
  // — which is the same information and unreadable, because nothing said which
  // value was which.
  const spend = usage && (() => {
    // Prefer the ledger (provider-reported tokens per call) when present; fall
    // back to the estimates for pre-ledger workspaces.
    const inTok = (usage.calls ?? []).reduce((n, c) => n + c.input_tokens, 0);
    const outTok = (usage.calls ?? []).reduce((n, c) => n + c.output_tokens, 0);
    const cost = usage.estimated_cost_usd;
    if (inTok + outTok > 0) {
      return `${inTok.toLocaleString()} in · ${outTok.toLocaleString()} out`
        + (typeof cost === "number" ? ` · ~$${cost.toFixed(4)}` : "");
    }
    return `~${usage.chat_tokens_approx.toLocaleString()} chat · ${usage.deep_run_tokens.toLocaleString()} deep`;
  })();

  const status = (
    // overflowWrap: a model id like llama-3.3-70b-versatile has no space to
    // break at, so on a narrow card it ran past the edge instead of wrapping.
    <dl className={s.statusGrid}>
      <dt className="eyebrow">Status</dt>
      <dd className="mono" style={{ color: data.configured ? "var(--verde)" : "var(--oxblood)" }}>
        {data.configured ? "ready" : "no key — Helix cannot answer in this workspace"}
      </dd>

      <dt className="eyebrow">Chat</dt>
      <dd className="mono">{data.effective_provider} / {data.effective_chat_model || "—"}</dd>

      <dt className="eyebrow">Deep Reasoning</dt>
      <dd className="mono">
        {data.deep_available ? data.effective_deep_model : "unavailable — needs a key or a local model"}
      </dd>

      <dt className="eyebrow">Configured by</dt>
      <dd className="mono">
        {data.source === "workspace" ? "this workspace" : "the server default"}
      </dd>

      {spend && (
        <>
          <dt className="eyebrow">Spend</dt>
          <dd className="mono"
            title="Lifetime spend on this workspace's key, as reported by the provider per call. Cost is an estimate from list prices.">
            {spend}
          </dd>
        </>
      )}
    </dl>
  );

  return (
    <>
      <div className={s.matrixHead} style={{ marginTop: 38 }}>
        <span className="serif-d" style={{ fontSize: 22 }}>Provider</span>
        <span className={`mono ${s.tag}`}>bring your own key</span>
      </div>
      <div className={s.row} style={{ flexDirection: "column", alignItems: "stretch", gap: 14 }}>
        {status}
        {isOwner && (
          <>
            {/* auto-fit, not a fixed pair: a text input's intrinsic width is
                about 200px, so two `1fr` tracks could not shrink below ~400px
                and ran the key field and both model fields off a narrow
                screen — where the card clips rather than scrolls. */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
              <Field label="Provider">
                <select
                  className={`mono ${s.roleSel}`}
                  value={provider}
                  onChange={(e) => { setProvider(e.target.value); setTestResult(null); }}
                >
                  {PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </Field>
              <Field label={data.api_key_masked ? `API key (stored: ${data.api_key_masked})` : "API key"}>
                <Input
                  type="password"
                  placeholder={data.api_key_masked ? "leave blank to keep the stored key" : "gsk_…"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  autoComplete="off"
                />
              </Field>
              {provider === "openai_compatible" && (
                <Field label="Base URL">
                  <Input placeholder="https://host/v1" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
                </Field>
              )}
              <Field label="Chat model">
                <Input placeholder="blank = default" value={chatModel} onChange={(e) => setChatModel(e.target.value)} />
              </Field>
              <Field label="Deep Reasoning model">
                <Input placeholder="blank = default" value={deepModel} onChange={(e) => setDeepModel(e.target.value)} />
              </Field>
            </div>

            {/* The consequence of the choice above, in plain words. */}
            <p className={s.posture}>{POSTURE[provider] ?? POSTURE[""]}</p>

            {/* "Test & save" is the primary, and says so. Both buttons were
                previously the same weight with near-identical labels, so the
                safe one — which proves the endpoint answers before it becomes
                this workspace's live configuration — read as the alternative. */}
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <Button variant="primary" disabled={saving} onClick={testAndSave}>
                Test &amp; save
              </Button>
              <Button variant="ghost" disabled={saving} onClick={() => save()}
                title="Store these settings without checking that the provider answers">
                Save without testing
              </Button>
              {data.api_key_masked && (
                <Button variant="ghost" disabled={saving} style={{ color: "var(--oxblood)" }}
                  onClick={() => save(true)}>Remove key</Button>
              )}
              {testResult && (
                <span className="mono" style={{ fontSize: 12, color: testResult.ok ? "var(--verde)" : "var(--oxblood)" }}>
                  {testResult.ok ? "✓" : "✕"} {testResult.detail}
                </span>
              )}
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
              The key is encrypted at rest and never returned by the API. Each workspace spends its
              own key. Ollama applies to self-hosted Helix — a hosted instance cannot reach your
              machine's localhost; point an OpenAI-compatible URL at a reachable endpoint instead.
            </div>
          </>
        )}
      </div>
    </>
  );
}
