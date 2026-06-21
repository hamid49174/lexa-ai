/* Unit-Test fuer die Datums-Gruppierung der Konversationsliste (chat_history_ui.js).
 * Laedt das echte Modul mit Stubs und prueft die pure Bucket-/Gruppierungs-Logik
 * (nowMs injiziert -> deterministisch, zeitzonen-stabil).
 */
const fs = require("fs");
const path = require("path");

let passed = 0, failed = 0;
function check(name, cond) {
  if (cond) { passed++; console.log("  ok: " + name); }
  else { failed++; console.log("  FAIL: " + name); }
}

const code = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "chat_history_ui.js"), "utf8");
const win = {};
// eslint-disable-next-line no-new-func
new Function("window", "document", "t", "showToast", "LexaState", "escapeHtml", code)(
  win, {}, (k) => k, () => {}, { get: () => null, set: () => {} }, (s) => s
);

check("exposes chatHistoryBucket", typeof win.chatHistoryBucket === "function");
check("exposes groupConversationsByDate", typeof win.groupConversationsByDate === "function");

// Fester Bezugspunkt: 16. Juni 2026, 12:00 Ortszeit (gleiche TZ wie die Eingabe-Strings).
const NOW = new Date(2026, 5, 16, 12, 0, 0).getTime();

check("bucket today", win.chatHistoryBucket("2026-06-16 09:00:00", NOW) === "today");
check("bucket yesterday", win.chatHistoryBucket("2026-06-15 23:00:00", NOW) === "yesterday");
check("bucket week", win.chatHistoryBucket("2026-06-12 10:00:00", NOW) === "week");
check("bucket month", win.chatHistoryBucket("2026-05-28 10:00:00", NOW) === "month");
check("bucket older", win.chatHistoryBucket("2026-01-01 10:00:00", NOW) === "older");
check("bucket invalid -> older", win.chatHistoryBucket("", NOW) === "older");
check("bucket ISO with T works", win.chatHistoryBucket("2026-06-16T08:00:00", NOW) === "today");

const convs = [
  { id: 1, updated_at: "2026-06-16 09:00:00" },               // today
  { id: 2, updated_at: "2026-06-15 22:00:00" },               // yesterday
  { id: 3, updated_at: "2026-06-12 10:00:00" },               // week
  { id: 4, updated_at: "2026-01-01 10:00:00" },               // older
  { id: 5, updated_at: "2026-06-01 10:00:00", is_pinned: 1 }, // pinned (eigene Gruppe)
];
const groups = win.groupConversationsByDate(convs, NOW);
check("pinned group first", groups[0].key === "pinned" && groups[0].items.length === 1 && groups[0].items[0].id === 5);
check("date groups in order", groups.slice(1).map((g) => g.key).join(",") === "today,yesterday,week,older");
check("empty buckets omitted (no 'month')", !groups.some((g) => g.key === "month"));
check("every non-pinned conv placed exactly once", groups.slice(1).reduce((n, g) => n + g.items.length, 0) === 4);
check("no pinned conv in date groups", !groups.slice(1).some((g) => g.items.some((c) => c.is_pinned)));

console.log("\n" + (passed + failed) + " tests: " + passed + " passed, " + failed + " failed");
if (failed > 0) process.exit(1);
