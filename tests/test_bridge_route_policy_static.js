/**
 * Static drift guard for preload bridge HTTP targets.
 * It catches policies that point at removed backend routes before Settings/UI
 * calls become runtime-only failures.
 */

const fs = require("fs");
const path = require("path");

const repoRoot = path.join(__dirname, "..");
const preloadSrc = fs.readFileSync(path.join(repoRoot, "frontend", "preload.js"), "utf8");
const backendDir = path.join(repoRoot, "backend");

let passed = 0;
let failed = 0;
function assert(desc, ok, detail = "") {
  if (ok) {
    console.log(`  ok: ${desc}`);
    passed += 1;
  } else {
    console.error(`  FAIL: ${desc}${detail ? " - " + detail : ""}`);
    failed += 1;
  }
}

function joinRoute(prefix, route) {
  const left = String(prefix || "").replace(/\/+$/, "");
  const right = String(route || "").replace(/^\/+/, "");
  if (!left && !right) return "/";
  if (!left) return `/${right}`;
  if (!right) return left || "/";
  return `${left}/${right}`;
}

function normalizeRoute(route) {
  const withoutQuery = String(route || "").split("?")[0].replace(/:.*$/, "");
  const collapsed = withoutQuery.replace(/\/+/g, "/").replace(/\/$/, "") || "/";
  return collapsed.replace(/\{[^}]+\}/g, "{}");
}

function routerPrefix(source) {
  const match = source.match(/router\s*=\s*APIRouter\(([\s\S]*?)\)/);
  if (!match) return "";
  const prefix = match[1].match(/prefix\s*=\s*["']([^"']*)["']/);
  return prefix ? prefix[1] : "";
}

function backendRoutes() {
  const routes = new Set();
  const files = fs.readdirSync(backendDir)
    .filter((name) => name === "main.py" || /^router_.*\.py$/.test(name));
  for (const file of files) {
    const source = fs.readFileSync(path.join(backendDir, file), "utf8");
    const prefix = routerPrefix(source);
    const routePattern = /@(router|app)\.(get|post|put|delete|patch)\(\s*["']([^"']*)["']/g;
    for (const match of source.matchAll(routePattern)) {
      const owner = match[1];
      const route = owner === "router" ? joinRoute(prefix, match[3]) : match[3];
      routes.add(normalizeRoute(route));
    }
  }
  return routes;
}

function bridgeHttpTargets() {
  return [...preloadSrc.matchAll(/bridgePolicy\("([^"]+)",\s*"([^"]+)",\s*"([^"]+)",\s*"([^"]+)"/g)]
    .map((match) => ({
      name: match[1],
      risk: match[2],
      actionType: match[3],
      target: match[4],
    }))
    .filter((entry) => entry.target.startsWith("/"))
    .map((entry) => ({
      ...entry,
      normalizedTarget: normalizeRoute(entry.target),
    }));
}

console.log("\nBridge route policy drift:");
const routes = backendRoutes();
const targets = bridgeHttpTargets();
const missing = targets.filter((entry) => !routes.has(entry.normalizedTarget));
assert(
  "all preload HTTP bridge targets exist in backend route declarations",
  missing.length === 0,
  missing.map((entry) => `${entry.name}:${entry.target}`).join(", "),
);

for (const target of ["/backup/create", "/backup/list", "/backup/restore-db"]) {
  assert(`settings backup target is backed by a route: ${target}`, routes.has(normalizeRoute(target)));
}

assert("bridge policies include HTTP targets to check", targets.length > 50);
assert("backend route parser found expected core routes", ["/chat", "/health", "/personal-os/status"].every((route) => routes.has(route)));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
