// Vendor the Google Fonts faces the app actually asks for into public/fonts,
// keeping only the latin + latin-ext subsets, and emit a local fonts.css.
import { writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const HREF = "https://fonts.googleapis.com/css2?family=Cinzel:wght@400;500;600;700&family=Cinzel+Decorative:wght@400;700;900&family=IM+Fell+English:ital@0;1&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap";
const OUT = process.argv[2];
mkdirSync(OUT, { recursive: true });

const css = await (await fetch(HREF, { headers: { "User-Agent": UA } })).text();

// Google emits: /* subset */\n@font-face { ... }
const blocks = [...css.matchAll(/\/\*\s*([a-z-]+)\s*\*\/\s*(@font-face\s*\{[^}]+\})/g)];
const KEEP = new Set(["latin", "latin-ext"]);
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
const out = [];
let bytes = 0, kept = 0, skipped = 0;

for (const [, subset, block] of blocks) {
  if (!KEEP.has(subset)) { skipped++; continue; }
  const fam = /font-family:\s*'([^']+)'/.exec(block)[1];
  const wght = /font-weight:\s*(\d+)/.exec(block)?.[1] ?? "400";
  const style = /font-style:\s*(\w+)/.exec(block)?.[1] ?? "normal";
  const url = /url\((https:[^)]+)\)/.exec(block)[1];
  const name = `${slug(fam)}-${wght}${style === "italic" ? "-italic" : ""}-${subset}.woff2`;
  const buf = Buffer.from(await (await fetch(url, { headers: { "User-Agent": UA } })).arrayBuffer());
  writeFileSync(join(OUT, name), buf);
  bytes += buf.length; kept++;
  out.push(block.replace(url, `/fonts/${name}`).replace(/^@font-face/, "@font-face"));
  console.log(`  ${name.padEnd(44)} ${(buf.length / 1024).toFixed(1)} KB`);
}
writeFileSync(join(OUT, "..", "..", "src", "styles", "fonts.css"),
`/* Self-hosted webfonts — vendored from Google Fonts, latin + latin-ext only.
   Self-hosted rather than linked because a self-hosted Helix must render its
   own typography offline and must not make every visitor's browser call a
   third party on page load. Regenerate with scripts/vendor-fonts.mjs. */
${out.join("\n")}
`, "utf-8");
console.log(`\n${kept} faces kept, ${skipped} non-latin subsets skipped, ${(bytes / 1024).toFixed(0)} KB total`);
