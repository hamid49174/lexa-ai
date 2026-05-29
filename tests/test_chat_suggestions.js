/**
 * Unit tests for assistant follow-up suggestion chips.
 * Run with: node tests/test_chat_suggestions.js
 */

const fs = require("fs");
const path = require("path");

const chatSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat.js"),
  "utf8"
);

function extractFn(source, name) {
  const needle = `function ${name}(`;
  const start = source.indexOf(needle);
  if (start === -1) throw new Error(`${name} not found`);
  let depth = 0;
  let seenBody = false;
  for (let i = start; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === "{") {
      depth += 1;
      seenBody = true;
    } else if (ch === "}") {
      depth -= 1;
      if (seenBody && depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`${name} body not found`);
}

const sandbox = new Function("t", `
  ${extractFn(chatSrc, "escapeSuggestionRegex")}
  ${extractFn(chatSrc, "chatSuggestionHasWord")}
  ${extractFn(chatSrc, "chatSuggestionHasAnyWord")}
  ${extractFn(chatSrc, "generateSuggestions")}
  return { generateSuggestions };
`);

const labels = {
  "chat.suggGoodnightRoutine": "Gute Nacht Routine",
  "chat.suggTimer10": "Timer 10 min",
  "chat.suggTellMore": "Erzaehl mir mehr",
  "chat.suggShowNotes": "Zeig meine Notizen",
  "chat.suggProcessList": "Prozessliste",
  "chat.suggDiskAnalysis": "Disk Analyse",
};
const { generateSuggestions } = sandbox((key) => labels[key] || key);

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

console.log("\nchat suggestions:");

const weatherSuggestions = generateSuggestions(
  "Hamburg: 14.9 C, Klar. Gefuehlt 14.9 C. Luftfeuchtigkeit 87%, Wind 6.5 km/h.",
  "wie ist wetter in hamburg"
);
assert(
  "plain weather answers do not get generic night or tell-more chips",
  weatherSuggestions.length === 0,
  JSON.stringify(weatherSuggestions)
);

const calorieSuggestions = generateSuggestions(
  "Kalorien sind Energie aus Lebensmitteln. Ueberschuss kann als Fett gespeichert werden.",
  "erklaer mir was kalorien sind"
);
assert(
  "calorie explanation does not trigger notes or system chips from gespeichert",
  !calorieSuggestions.includes("Zeig meine Notizen")
    && !calorieSuggestions.includes("Prozessliste")
    && !calorieSuggestions.includes("Disk Analyse"),
  JSON.stringify(calorieSuggestions)
);

const systemSuggestions = generateSuggestions("CPU 20%, RAM 50%, Speicher okay.", "systeminfo");
assert(
  "real system answers still get system chips",
  systemSuggestions.includes("Prozessliste") && systemSuggestions.includes("Disk Analyse"),
  JSON.stringify(systemSuggestions)
);

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
