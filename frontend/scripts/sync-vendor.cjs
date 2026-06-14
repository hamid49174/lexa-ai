const fs = require("fs");
const path = require("path");

const frontendRoot = path.resolve(__dirname, "..");
const vendorRoot = path.join(frontendRoot, "src", "vendor");
const checkOnly = process.argv.includes("--check");

const assets = [
  {
    label: "three",
    source: path.join(frontendRoot, "node_modules", "three", "build", "three.min.js"),
    target: path.join(vendorRoot, "three.min.js"),
  },
  {
    label: "simplex-noise",
    source: path.join(frontendRoot, "node_modules", "simplex-noise", "simplex-noise.js"),
    target: path.join(vendorRoot, "simplex-noise.js"),
  },
  {
    label: "highlight.js",
    source: path.join(frontendRoot, "node_modules", "@highlightjs", "cdn-assets", "highlight.min.js"),
    target: path.join(vendorRoot, "highlight.min.js"),
  },
  {
    label: "highlight.js-theme (github-dark)",
    source: path.join(frontendRoot, "node_modules", "@highlightjs", "cdn-assets", "styles", "github-dark.min.css"),
    target: path.join(vendorRoot, "highlight-github-dark.min.css"),
  },
  {
    label: "katex.js",
    source: path.join(frontendRoot, "node_modules", "katex", "dist", "katex.min.js"),
    target: path.join(vendorRoot, "katex", "katex.min.js"),
  },
  {
    label: "katex.css",
    source: path.join(frontendRoot, "node_modules", "katex", "dist", "katex.min.css"),
    target: path.join(vendorRoot, "katex", "katex.min.css"),
  },
  {
    label: "katex-auto-render",
    source: path.join(frontendRoot, "node_modules", "katex", "dist", "contrib", "auto-render.min.js"),
    target: path.join(vendorRoot, "katex", "auto-render.min.js"),
  },
];

function fail(message) {
  console.error(message);
  process.exit(1);
}

for (const asset of assets) {
  if (!fs.existsSync(asset.source)) {
    fail(`Vendor source missing for ${asset.label}: ${asset.source}`);
  }
}

if (!checkOnly) {
  fs.mkdirSync(vendorRoot, { recursive: true });
}

const drift = [];
for (const asset of assets) {
  const source = fs.readFileSync(asset.source);
  const targetExists = fs.existsSync(asset.target);
  const target = targetExists ? fs.readFileSync(asset.target) : Buffer.alloc(0);

  if (Buffer.compare(source, target) === 0) {
    continue;
  }

  if (checkOnly) {
    drift.push(asset.target);
    continue;
  }

  fs.mkdirSync(path.dirname(asset.target), { recursive: true });
  fs.writeFileSync(asset.target, source);
  console.log(`synced ${path.relative(frontendRoot, asset.target)} from ${asset.label}`);
}

// KaTeX-Schriftarten (woff2 reicht fuer Chromium/Electron) — komplettes fonts-Verzeichnis
const katexFontsSrc = path.join(frontendRoot, "node_modules", "katex", "dist", "fonts");
const katexFontsDst = path.join(vendorRoot, "katex", "fonts");
if (!fs.existsSync(katexFontsSrc)) {
  fail(`Vendor source missing for katex-fonts: ${katexFontsSrc}`);
}
if (!checkOnly) {
  fs.mkdirSync(katexFontsDst, { recursive: true });
}
for (const fontFile of fs.readdirSync(katexFontsSrc)) {
  if (!/\.woff2$/i.test(fontFile)) continue;
  const fSrc = fs.readFileSync(path.join(katexFontsSrc, fontFile));
  const fDstPath = path.join(katexFontsDst, fontFile);
  const fDst = fs.existsSync(fDstPath) ? fs.readFileSync(fDstPath) : Buffer.alloc(0);
  if (Buffer.compare(fSrc, fDst) === 0) continue;
  if (checkOnly) { drift.push(fDstPath); continue; }
  fs.writeFileSync(fDstPath, fSrc);
  console.log(`synced ${path.relative(frontendRoot, fDstPath)}`);
}

if (drift.length > 0) {
  fail(`Bundled vendor assets are stale. Run: npm --prefix frontend run sync-vendor\n${drift.join("\n")}`);
}

console.log(checkOnly ? "Bundled vendor assets are current." : "Bundled vendor assets synced.");
