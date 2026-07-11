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

  async function saveAndTest() {
    if (!(await save())) return;
    try {
      setTestResult(await testProviderSettings(wid));
    } catch (e: any) {
      setTestResult({ ok: false, detail: e?.message ?? "Test failed" });
    }
  }

  if (isLoading || !data) return <Spinner />;

  const status = (
    <div style={{ fontSize: 13, color: "var(--ink-2)", display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
      <span className="mono" style={{ color: data.configured ? "var(--verde)" : "var(--oxblood)" }}>
        {data.configured ? "● ready" : "○ no key"}
      </span>
      <span>chat: <span className="mono">{data.effective_provider} / {data.effective_chat_model || "—"}</span></span>
      <span>deep: <span className="mono">{data.deep_available ? data.effective_deep_model : "unavailable (needs a Groq key)"}</span></span>
      <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
        {data.source === "workspace" ? "workspace settings" : "server default"}
      </span>
      {usage && (
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}
          title="Lifetime spend on this workspace's key. Chat is approximate (streamed chunk count); deep-run tokens are measured.">
          spend: ~{usage.chat_tokens_approx.toLocaleString()} chat · {usage.deep_run_tokens.toLocaleString()} deep
        </span>
      )}
    </div>
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
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
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
              <Field label="Chat model (blank = default)">
                <Input placeholder="llama-3.1-8b-instant" value={chatModel} onChange={(e) => setChatModel(e.target.value)} />
              </Field>
              <Field label="Deep Reasoning model (blank = default)">
                <Input placeholder="llama-3.3-70b-versatile" value={deepModel} onChange={(e) => setDeepModel(e.target.value)} />
              </Field>
            </div>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <Button variant="primary" disabled={saving} onClick={() => save()}>Save</Button>
              <Button disabled={saving} onClick={saveAndTest}>Save &amp; test connection</Button>
              {data.api_key_masked && (
                <Button variant="ghost" disabled={saving} onClick={() => save(true)}>Remove key</Button>
              )}
              {testResult && (
                <span className="mono" style={{ fontSize: 12.5, color: testResult.ok ? "var(--verde)" : "var(--oxblood)" }}>
                  {testResult.ok ? "✓" : "✕"} {testResult.detail}
                </span>
              )}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
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
