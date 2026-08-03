// Dark-mode ("nocturne") re-capture of the same eight frames e2e/smoke.mjs
// produces. Same flow, same viewport, same assertions — the only difference is
// that the theme is forced to dark before first paint, so every shot is the
// nocturne variant of the light one.
//
// Run from frontend/app:  node e2e/shots-dark.mjs [outDir]
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

const repo = resolve(import.meta.dirname, "..", "..", "..");
const shots = process.argv[2] ? resolve(process.argv[2]) : join(repo, "docs", "screenshots-dark");
mkdirSync(shots, { recursive: true });

const API = "http://127.0.0.1:8000";
const UI = "http://localhost:5173";
const dbFile = join(tmpdir(), `helix-dark-${Date.now()}.db`);
const children = [];

function boot(cmd, args, opts) {
  const child = spawn(cmd, args, { stdio: "ignore", ...opts });
  children.push(child);
  return child;
}

// taskkill /T takes the whole tree down. Resolves only once taskkill has
// actually exited — exiting the process before then leaves vite holding 5173,
// and the next run boots against a stale frontend.
function killTree(pid) {
  return new Promise((done) => {
    try {
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" })
        .on("close", done).on("error", done);
    } catch { done(); }
  });
}

async function waitFor(url, label, tries = 240) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`${label} never came up at ${url}`);
}

const step = (msg) => console.log(`  • ${msg}`);

async function main() {
  boot(join(repo, "backend", ".venv", "Scripts", "python.exe"),
    ["-m", "uvicorn", "api.main:app", "--port", "8000"],
    { cwd: join(repo, "backend"), env: { ...process.env, HELIX_DEV: "1", DATABASE_URL: `sqlite+aiosqlite:///${dbFile.replace(/\\/g, "/")}` } });
  boot("npm", ["run", "dev"], { cwd: join(repo, "frontend", "app"), shell: true });
  await waitFor(`${API}/health`, "backend");
  await waitFor(UI, "frontend");
  step("backend + frontend up");

  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.setDefaultTimeout(30_000);
  // Nocturne before first paint: initTheme() reads this key on boot, so no
  // click on the ☾ toggle is needed and no frame is captured mid-transition.
  await page.addInitScript(() => localStorage.setItem("helix:theme", "dark"));
  failShot = () => page.screenshot({ path: join(shots, "99-failure.png") }).catch(() => {});

  // --- register ---
  await page.goto(`${UI}/auth`);
  const theme = await page.evaluate(() => document.documentElement.dataset.theme);
  if (theme !== "dark") throw new Error(`theme did not apply (data-theme=${theme})`);
  step("nocturne applied");
  const tab = page.getByRole("tab", { name: "Create account" });
  await tab.click();
  await page.locator('input[type="email"]').fill("aria@helix.team");
  await page.locator('input[type="password"]').fill("demo-password-1");
  // The tab pill is a Framer spring and the helix mark draws itself on: shoot
  // too early and the pill is caught between the two tabs with the helix half
  // drawn. Wait, then confirm the pill's box sits inside the active tab's.
  await new Promise((r) => setTimeout(r, 1_500));
  const settled = await tab.evaluate((el) => {
    const pill = el.parentElement.querySelector('[class*="pill"], [style*="transform"]');
    const t = el.getBoundingClientRect();
    const p = pill?.getBoundingClientRect();
    return p ? p.left >= t.left - 8 && p.right <= t.right + 8 : null;
  });
  if (settled === false) throw new Error("tab pill never settled on the active tab");
  await page.screenshot({ path: join(shots, "01-signin.png") });
  await page.getByRole("button", { name: /Create account ⟶/ }).click();
  // /health answers as soon as the server binds, but the FIRST real request
  // sits behind lazy init (the embedder, the provider client), and on a cold
  // machine that outlasts the 30s default while the button just shows "…".
  // Wait on the navigation, not on the next control.
  await page.waitForURL(/\/workspaces/, { timeout: 120_000 });
  step("registered");

  // --- workspace ---
  await page.getByRole("button", { name: "+ New workspace" }).click();
  await page.getByPlaceholder(/Workspace name/).fill("rag-quality");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByRole("button", { name: /rag-quality/ }).first().click().catch(() => {});
  step("workspace created");

  // --- first conversation, streamed reply ---
  await page.getByRole("button", { name: "Begin a conversation" }).click();
  await page.getByPlaceholder(/Title \(e\.g\./).fill("Chunking strategy");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  const composer = page.getByPlaceholder(/Continue the thread/);
  async function ask(text) {
    await composer.fill(text);
    await composer.press("Enter");
    await page.waitForFunction(
      (sel) => !document.querySelector(sel)?.disabled,
      'button[title="Send (Enter)"]', { timeout: 90_000 });
  }
  await ask("Our RAG product retrieves the wrong passage about 30% of the time. How should we chunk documents to improve recall?");
  step("chat reply streamed");

  // --- knowledge base upload ---
  const spec = join(tmpdir(), "retrieval-spec.md");
  writeFileSync(spec, [
    "# Retrieval spec — chunking and recall",
    "",
    "Documents are chunked at 800 characters with 15% overlap. Recall is",
    "measured on the golden retrieval set; the hybrid arm fuses dense",
    "MiniLM cosine scores with BM25 via reciprocal rank fusion (RRF).",
    "Chunks below the measured relevance floor of 0.20 are never included",
    "in grounding. The embedder is all-MiniLM-L6-v2, versioned per row.",
  ].join("\n"));
  await page.getByRole("button", { name: "DOCS", exact: true }).click();
  await page.locator('input[type="file"]').first().setInputFiles(spec);
  await page.getByText("ready", { exact: false }).first().waitFor({ timeout: 120_000 });
  await page.screenshot({ path: join(shots, "05-docs.png") });
  step("document ingested");

  // --- cited grounding ---
  await page.getByRole("button", { name: "CHAT", exact: true }).click();
  await page.getByText("Chunking strategy").first().click();
  await page.getByText(/\d+ nodes/).first().waitFor();
  await page.getByText("Ingesting", { exact: false }).waitFor({ state: "hidden", timeout: 15_000 }).catch(() => {});
  await ask("What relevance floor and overlap does our retrieval spec use for chunking?");
  await page.getByText("grounded on").first().waitFor();
  await page.screenshot({ path: join(shots, "02-grounded-chat.png") });
  step("citation chips shown");

  // --- proactive resurfacing (typed, not sent) ---
  await page.locator('button[title="New conversation"]').click();
  await page.getByPlaceholder(/Title \(e\.g\./).fill("Recall experiments");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByText("Recall experiments").first().waitFor();
  await composer.fill("What chunk size should we use to get the best retrieval recall?");
  await page.getByText("explored before").waitFor({ timeout: 30_000 });
  await page.screenshot({ path: join(shots, "03-resurfacing.png") });
  await composer.fill("");
  step("resurfacing strip appeared");

  // --- agent run with tool ledger ---
  await composer.fill("Search our knowledge base and past threads: what do we already know about chunking and recall?");
  await page.getByRole("button", { name: /Agent/ }).click();
  await page.locator("text=⚒ search_").first().waitFor({ timeout: 90_000 });
  await page.waitForFunction(
    (sel) => !document.querySelector(sel)?.disabled,
    'button[title="Send (Enter)"]', { timeout: 120_000 });
  await page.screenshot({ path: join(shots, "04-agent-ledger.png") });
  step("agent run: tool ledger rendered");

  // --- deep reasoning (the 70B may be rate-limited) ---
  try {
    await composer.fill("Is our 30% retrieval failure more likely a chunking problem or an embedding problem? Argue it out.");
    await page.getByRole("button", { name: "Deep Reasoning" }).click();
    await page.getByText(/step \d+ · depth/).first().waitFor({ timeout: 90_000 });
    await new Promise((r) => setTimeout(r, 8_000)); // let a few trace steps land
    await page.screenshot({ path: join(shots, "06-deep-monitor.png") });
    step("deep reasoning monitor captured");
  } catch (e) {
    step(`deep reasoning FAILED (${e.message.split("\n")[0]}) — shot missing`);
  }

  // --- map + tools panel ---
  await page.getByRole("button", { name: "MAP", exact: true }).click();
  await new Promise((r) => setTimeout(r, 2_500)); // layout settle
  await page.screenshot({ path: join(shots, "07-map.png") });
  await page.getByRole("button", { name: "TEAM", exact: true }).click();
  await page.getByText("Agent tools").first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(shots, "08-tools-panel.png") });
  step("map + tools panel captured");

  await browser.close();
  console.log(`\nDark click-through PASSED. Screenshots in ${shots}`);
}

let failShot = async () => {};
let browser;
main()
  .catch(async (e) => {
    console.error("\nDark click-through FAILED:", e.message);
    await failShot();
    process.exitCode = 1;
  })
  .finally(async () => {
    // On the failure path main() never reached its browser.close(), and an open
    // Playwright browser keeps the event loop alive forever — the run would sit
    // there wedged instead of reporting. Close it here, then exit explicitly so
    // a stray handle can't hold the process open either way.
    await browser?.close().catch(() => {});
    await Promise.all(children.map((c) => killTree(c.pid)));
    // The backend may still hold the SQLite handle for a moment; a leftover
    // file in the temp dir is not worth delaying the exit over.
    try { rmSync(dbFile, { force: true }); } catch { /* it's in tmp */ }
    process.exit(process.exitCode ?? 0);
  });
