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

  fs.writeFileSync(asset.target, source);
  console.log(`synced ${path.relative(frontendRoot, asset.target)} from ${asset.label}`);
}

if (drift.length > 0) {
  fail(`Bundled vendor assets are stale. Run: npm --prefix frontend run sync-vendor\n${drift.join("\n")}`);
}

console.log(checkOnly ? "Bundled vendor assets are current." : "Bundled vendor assets synced.");
