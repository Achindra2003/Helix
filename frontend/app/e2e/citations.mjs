// The claim this whole pass rests on: a grounded answer keeps its evidence.
//
// It used to not. The `grounding` SSE frame reached the browser, ChatView held
// it in a module-level record, and a reload dropped it — the reply survived,
// the sources for it did not. A unit test can prove the row is written; only a
// real browser can prove the chips are still on screen after F5, because the
// bug lived in the gap between the two.
//
// Also asserts the second half of the fix: that the exported record carries the
// sources too, and that a catalogued document is cited as a reference rather
// than as a filename.
//
// Ports 8021/5181 so nothing else in the repo collides. No LLM key needed —
// the stub provider answers, and grounding is retrieval, not generation.
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

const repo = resolve(import.meta.dirname, "..", "..", "..");
const API = "http://127.0.0.1:8021";
const UI = "http://localhost:5181";
const dbFile = join(tmpdir(), `helix-citations-${Date.now()}.db`);
const children = [];
const failures = [];

function boot(cmd, args, opts) {
  const child = spawn(cmd, args, { stdio: "ignore", ...opts });
  children.push(child);
  return child;
}

function killTree(pid) {
  return new Promise((done) => {
    try {
      if (process.platform === "win32") {
        spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" })
          .on("close", done);
      } else {
        process.kill(-pid, "SIGKILL");
        done();
      }
    } catch { done(); }
  });
}

async function waitFor(url, label, tries = 160) {
  for (let i = 0; i < tries; i++) {
    try { if ((await fetch(url)).ok) return; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`${label} never came up at ${url}`);
}

function check(ok, label) {
  console.log(`  ${ok ? "ok  " : "FAIL"} ${label}`);
  if (!ok) failures.push(label);
}

const DOC = `Retrieval-augmented generation grounds a model's answer in
retrieved passages. The relevance floor is calibrated on a golden set so an
unrelated question does not drag the knowledge base into its prompt. Chunk
overlap of fifty tokens preserved cross-section context in our measurements.`;

let browser;
async function main() {
  boot(join(repo, "backend", ".venv", "Scripts", "python.exe"),
    ["-m", "uvicorn", "api.main:app", "--port", "8021"],
    { cwd: join(repo, "backend"), env: {
      ...process.env, LLM_PROVIDER: "stub", HELIX_DEV: "1", FRONTEND_BASE_URL: UI,
      DOCUMENTS_INGEST_INLINE: "1",
      DATABASE_URL: `sqlite+aiosqlite:///${dbFile.replace(/\\/g, "/")}`,
    } });
  boot("npx", ["vite", "--port", "5181", "--strictPort"],
    { cwd: join(repo, "frontend", "app"), shell: true, env: { ...process.env, VITE_API_BASE: API } });
  await waitFor(`${API}/health`, "backend");
  await waitFor(UI, "frontend");

  browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.setDefaultTimeout(30_000);

  // --- sign in ---------------------------------------------------------------
  await page.goto(`${UI}/auth`);
  await page.getByRole("tab", { name: "Create account" }).click();
  await page.locator('input[type="email"]').fill("cites@helix.team");
  await page.locator('input[type="password"]').fill("demo-password-1");
  await page.getByRole("button", { name: /Create account ⟶/ }).click();
  await page.waitForURL(/\/workspaces|\/w\//, { timeout: 120_000 });

  const token = await page.evaluate(() => JSON.parse(
    localStorage.getItem("helix.session") ?? "{}").state?.token
    ?? localStorage.getItem("helix.token"));

  // A workspace and a document, over the API — the UI paths for both are
  // covered elsewhere, and this run is about what happens to a citation.
  const auth = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const ws = await (await fetch(`${API}/api/workspaces`, {
    method: "POST", headers: auth, body: JSON.stringify({ name: "Citations" }),
  })).json();
  const wid = ws.id;

  const form = new FormData();
  form.append("file", new Blob([DOC], { type: "text/plain" }), "rag-notes.txt");
  const doc = await (await fetch(`${API}/api/workspaces/${wid}/documents`, {
    method: "POST", headers: { Authorization: `Bearer ${token}` }, body: form,
  })).json();
  check(doc.status === "ready", `the document ingested (${doc.chunk_count} chunks)`);

  // A fresh workspace has no thread, so there is no composer to type into.
  await (await fetch(`${API}/conversations`, {
    method: "POST", headers: auth,
    body: JSON.stringify({ workspace_id: wid, title: "Grounding" }),
  })).json();

  // --- ask something the document answers ------------------------------------
  console.log("\na grounded reply shows its sources");
  await page.goto(`${UI}/w/${wid}`);
  await page.waitForTimeout(2000);
  await page.locator("textarea").first().fill("what is the relevance floor calibrated on?");
  await page.locator("textarea").first().press("Enter");
  await page.waitForTimeout(6000);

  // Case-insensitive: the label is uppercased by CSS, so innerText reads
  // "GROUNDED ON" even though the markup says otherwise.
  const chip = page.locator("text=/grounded on/i").first();
  check(await chip.count() > 0, "the reply carries a 'grounded on' row");
  const before = await page.evaluate(() => document.body.innerText);
  check(/rag-notes\.txt/.test(before), "and names the document it used");

  // --- THE test --------------------------------------------------------------
  console.log("\nand still shows them after a reload");
  await page.reload();
  await page.waitForTimeout(6000);
  const after = await page.evaluate(() => document.body.innerText);
  check(/grounded on/i.test(after), "the 'grounded on' row survives a reload");
  check(/rag-notes\.txt/.test(after), "and still names the document");

  // --- the record that leaves the building ------------------------------------
  console.log("\nthe export carries the evidence too");
  const convs = await (await fetch(`${API}/conversations?workspace_id=${wid}`, { headers: auth })).json();
  const cid = convs.items[0].id;
  const md = await (await fetch(`${API}/conversations/${cid}/export`, { headers: auth })).text();
  check(/Grounded on:/.test(md), "the decision report has a sources section");
  check(/rag-notes\.txt/.test(md), "naming the document the answer rested on");

  // --- catalogue it, and the citation becomes a reference ---------------------
  console.log("\na catalogued source is cited as a reference");
  await fetch(`${API}/api/workspaces/${wid}/documents/${doc.id}`, {
    method: "PATCH", headers: auth,
    body: JSON.stringify({ authors: "Lewis et al.", year: "2020" }),
  });
  await page.goto(`${UI}/w/${wid}`);
  await page.waitForTimeout(1200);
  await page.locator("textarea").first().fill("what did chunk overlap preserve?");
  await page.locator("textarea").first().press("Enter");
  await page.waitForTimeout(6000);
  const cited = await page.evaluate(() => document.body.innerText);
  check(/Lewis et al\. \(2020\)/.test(cited), "the chip reads as a reference, not a filename");

  // Older answers keep the name they were given: a record says what it cited
  // on the day it was written.
  check(/rag-notes\.txt/.test(cited), "and the earlier reply keeps the name it was given");
}

main()
  .catch((err) => { console.error("\n" + err.stack); failures.push(String(err.message)); })
  .finally(async () => {
    if (browser) await browser.close();
    await Promise.all(children.map((c) => killTree(c.pid)));
    console.log(
      failures.length
        ? `\n${failures.length} FAILED:\n  - ${failures.join("\n  - ")}`
        : "\nall checks passed",
    );
    process.exit(failures.length ? 1 : 0);
  });
