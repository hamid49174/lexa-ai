const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "..", "..");
const backendBundle = path.join(repoRoot, "backend-dist", "lexa-backend", "lexa-backend.exe");

if (!fs.existsSync(backendBundle)) {
  console.error("Backend bundle missing:");
  console.error(`  ${backendBundle}`);
  console.error("");
  console.error("Run from the repository root first:");
  console.error("  powershell -ExecutionPolicy Bypass -File scripts\\build_installer.ps1");
  process.exit(1);
}
