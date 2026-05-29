/**
 * Static checks for the Obsidian-style Memory/Gedaechtnis graph view.
 * Run with: node tests\test_memory_graph_static.js
 */

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend", "src", "index.html"), "utf8");
const memorySrc = fs.readFileSync(path.join(root, "frontend", "src", "memory.js"), "utf8");
const viewsCss = [
  fs.readFileSync(path.join(root, "frontend", "src", "css", "views.css"), "utf8"),
  fs.readFileSync(path.join(root, "frontend", "src", "css", "views_memory.css"), "utf8"),
].join("\n");
const preloadSrc = fs.readFileSync(path.join(root, "frontend", "preload.js"), "utf8");

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

const memoryStart = html.indexOf('<div class="tool-view" id="memory-view">');
const memoryEnd = html.indexOf("<!-- Personal OS View -->", memoryStart);
const memoryView = memoryStart >= 0 && memoryEnd > memoryStart ? html.slice(memoryStart, memoryEnd) : "";
const removedDashboardIds = [
  "memory-stats-grid",
  "notes-list",
  "snippets-list",
  "ai-status-panel",
  "routines-list",
  "clipboard-history-list",
  "memory-cleanup-info",
];

console.log("\nMemory graph static checks:");
assert("Memory view section is present", Boolean(memoryView));
assert("Memory view uses graph shell", memoryView.includes("memory-graph-shell") && memoryView.includes("memory-graph-svg"));
assert("Memory view has graph search and fit controls", memoryView.includes("memory-graph-filter") && memoryView.includes("memory-graph-fit-btn"));
assert("Memory view has hover inspector and legend", memoryView.includes("memory-graph-inspector") && memoryView.includes("memory-graph-legend"));
assert("Old visible Memory dashboard sections are removed", removedDashboardIds.every((id) => !memoryView.includes(id)), removedDashboardIds.filter((id) => memoryView.includes(id)).join(", "));

assert("Preload exposes low-risk read-only memoryGraph bridge method", preloadSrc.includes('bridgePolicy("memoryGraph", "low", "read", "/memory/graph"') && preloadSrc.includes("memoryGraph: async (limit = 160)"));
assert("memoryGraph bridge calls the read-only backend endpoint", preloadSrc.includes("/memory/graph?limit=") && preloadSrc.includes("fetchWithTimeout"));
assert("Smoke mock includes unsafe graph text for renderer escaping coverage", preloadSrc.includes("note:unsafe-smoke") && preloadSrc.includes("<script>alert(1)</script>"));

assert("Renderer fetches and renders memoryGraph payload", memorySrc.includes("window.lexa.memoryGraph(180)") && memorySrc.includes("function renderMemoryGraph(data)"));
assert("Renderer falls back to legacy read endpoints when graph endpoint is unavailable", memorySrc.includes("function loadMemoryGraphFallbackData(") && memorySrc.includes("function buildMemoryGraphFallbackData(") && memorySrc.includes("await loadMemoryGraphFallbackData()"));
assert("Fallback graph uses only existing read surfaces", ["window.lexa.memoryStats", "window.lexa.notes", "window.lexa.snippets", "window.lexa.routines", "window.lexa.conversations"].every((needle) => memorySrc.includes(needle)));
assert("Renderer uses SVG DOM APIs rather than innerHTML for graph nodes", memorySrc.includes("document.createElementNS(MEMORY_GRAPH_NS") && memorySrc.includes("label.textContent = node.label") && !memorySrc.includes("memory-graph-svg.innerHTML"));
assert("Renderer sanitizes graph class tokens", memorySrc.includes("function memoryGraphClassToken(") && memorySrc.includes("replace(/[^a-z0-9_-]+/g"));
assert("Renderer supports Obsidian-style focus/filter/fit interactions", memorySrc.includes("function memoryGraphApplyFocus(") && memorySrc.includes('document.getElementById("memory-graph-filter")') && memorySrc.includes('document.getElementById("memory-graph-fit-btn")'));
assert("Renderer stops graph animation away from Memory view", memorySrc.includes('LexaState.get("currentView") !== "memory"') && memorySrc.includes("cancelAnimationFrame(memoryGraphState.frame)"));

assert("Graph CSS owns the Memory view surface", viewsCss.includes("#memory-view") && viewsCss.includes(".memory-graph-shell") && viewsCss.includes(".memory-graph-stage"));
assert("Graph CSS styles nodes, links, inspector, and legend", [".memory-graph-node", ".memory-graph-link", ".memory-graph-inspector", ".memory-graph-legend"].every((selector) => viewsCss.includes(selector)));
assert("Graph CSS avoids decorative card dashboard layout for Memory view", !memoryView.includes("memory-section") && !memoryView.includes("info-grid"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
