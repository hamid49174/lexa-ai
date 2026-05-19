/**
 * Static and helper tests for Personal OS preload response handling.
 * Run with: node tests/test_preload_personal_os_static.js
 */

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "preload.js"),
  "utf8"
);

function extractFn(source, name) {
  const needles = [`async function ${name}(`, `function ${name}(`];
  const start = needles
    .map((needle) => source.indexOf(needle))
    .filter((index) => index >= 0)
    .sort((a, b) => a - b)[0];
  if (start === undefined) throw new Error(`'${name}' not found`);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`No closing brace for '${name}'`);
}

const sandbox = new Function(`
  "use strict";
  ${extractFn(src, "apiErrorText")}
  ${extractFn(src, "apiRequestId")}
  ${extractFn(src, "apiJson")}
  ${extractFn(src, "personalOsErrorText")}
  ${extractFn(src, "personalOsJson")}
  ${extractFn(src, "personalOsRetryDelayMs")}
  let fetchResponses = [];
  let fetchCalls = [];
  let retryDelays = [];
  async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
    fetchCalls.push({ url, options, timeoutMs });
    const next = fetchResponses.shift();
    if (!next) throw new Error("missing fake response");
    return next;
  }
  function personalOsDelay(ms) {
    retryDelays.push(ms);
    return Promise.resolve();
  }
  ${extractFn(src, "personalOsFetchJsonWithRetry")}
  function setFetchResponses(items) {
    fetchResponses = items.slice();
    fetchCalls = [];
    retryDelays = [];
  }
  return {
    personalOsErrorText,
    apiJson,
    personalOsJson,
    personalOsRetryDelayMs,
    personalOsFetchJsonWithRetry,
    setFetchResponses,
    fetchCalls: () => fetchCalls,
    retryDelays: () => retryDelays,
  };
`);

const {
  personalOsErrorText,
  apiJson,
  personalOsJson,
  personalOsRetryDelayMs,
  personalOsFetchJsonWithRetry,
  setFetchResponses,
  fetchCalls,
  retryDelays,
} = sandbox();

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

function response({ ok, status, payload, jsonError = false, requestId = "" }) {
  return {
    ok,
    status,
    headers: {
      get(name) {
        return name && name.toLowerCase() === "x-request-id" ? requestId : "";
      },
    },
    async json() {
      if (jsonError) throw new Error("invalid json");
      return payload;
    },
  };
}

function responseWithHeaders({ ok, status, payload, headers = {} }) {
  return {
    ok,
    status,
    headers: {
      get(name) {
        return headers[String(name || "").toLowerCase()] || "";
      },
    },
    async json() {
      return payload;
    },
  };
}

(async () => {
  console.log("\npersonalOsErrorText():");
  assert("keeps string details", personalOsErrorText("Invalid tag filter") === "Invalid tag filter");
  assert("keeps object message details", personalOsErrorText({ message: "MCP offline" }) === "MCP offline");
  assert("formats validation detail arrays", personalOsErrorText([{ loc: ["query", "tag"], msg: "Invalid tag filter" }]) === "query.tag: Invalid tag filter");
  assert("serializes unknown objects", personalOsErrorText({ detail: "nested" }).includes("nested"));

  console.log("\npersonalOsJson():");
  const okPayload = await personalOsJson(response({ ok: true, status: 200, payload: { ok: true, value: 42 } }));
  assert("returns successful payloads unchanged", okPayload.ok === true && okPayload.value === 42);

  const badSuccessPayload = await personalOsJson(response({ ok: true, status: 200, payload: null, jsonError: true }), "Status failed");
  assert("turns malformed success JSON into ok false", badSuccessPayload.ok === false && badSuccessPayload.httpStatus === 200);
  assert("explains malformed success JSON", badSuccessPayload.error === "Status failed: invalid JSON response", badSuccessPayload.error);

  const errorPayload = await personalOsJson(response({ ok: false, status: 400, payload: { error: "Invalid tag filter" }, requestId: "req-123" }), "Query failed");
  assert("turns HTTP error JSON into ok false", errorPayload.ok === false && errorPayload.httpStatus === 400);
  assert("keeps backend error text", errorPayload.error === "Invalid tag filter", errorPayload.error);
  assert("keeps backend request id", errorPayload.requestId === "req-123", errorPayload.requestId);

  const canonicalPayload = await apiJson(response({
    ok: false,
    status: 429,
    payload: {
      ok: false,
      status: "error",
      error: "Zu viele Anfragen.",
      message: "Zu viele Anfragen.",
      errorCode: "rate_limited",
      httpStatus: 429,
      requestId: "req-body",
      retryable: true,
    },
    requestId: "req-header",
  }), "Request failed");
  assert("keeps canonical backend error code", canonicalPayload.errorCode === "rate_limited", canonicalPayload.errorCode);
  assert("prefers canonical body request id", canonicalPayload.requestId === "req-body", canonicalPayload.requestId);
  assert("keeps retryable flag from canonical payload", canonicalPayload.retryable === true);

  const detailPayload = await personalOsJson(response({ ok: false, status: 502, payload: { detail: { message: "MCP disconnected" } } }), "Tool failed");
  assert("extracts structured detail messages", detailPayload.error === "MCP disconnected", detailPayload.error);

  const validationPayload = await personalOsJson(response({ ok: false, status: 422, payload: { detail: [{ loc: ["query", "tag"], msg: "Invalid tag filter" }] } }), "Query failed");
  assert("extracts validation detail arrays", validationPayload.error === "query.tag: Invalid tag filter", validationPayload.error);

  const malformedPayload = await personalOsJson(response({ ok: false, status: 500, payload: null, jsonError: true }), "Context map failed");
  assert("falls back when error JSON is malformed", malformedPayload.error === "Context map failed (HTTP 500)", malformedPayload.error);

  console.log("\npersonalOsFetchJsonWithRetry():");
  assert("parses retry-after seconds with bounds", personalOsRetryDelayMs(responseWithHeaders({ ok: false, status: 429, payload: {}, headers: { "retry-after": "2" } })) === 2000);
  setFetchResponses([
    responseWithHeaders({ ok: false, status: 429, payload: { detail: "Too many requests" }, headers: { "retry-after": "0.5" } }),
    responseWithHeaders({ ok: true, status: 200, payload: { ok: true, state: "attention" } }),
  ]);
  const retried = await personalOsFetchJsonWithRetry("/personal-os/diagnostics", "Diagnostics failed", {}, 1234, { attempts: 2, statuses: [429], delayMs: 1200 });
  assert("retries transient diagnostics rate limits", retried.ok === true && retried.state === "attention" && fetchCalls().length === 2);
  assert("uses retry-after delay before retrying", retryDelays()[0] === 500, `delay=${retryDelays()[0]}`);
  setFetchResponses([
    responseWithHeaders({ ok: false, status: 500, payload: { detail: "MCP failed" } }),
  ]);
  const notRetried = await personalOsFetchJsonWithRetry("/personal-os/diagnostics", "Diagnostics failed", {}, 1234, { attempts: 2, statuses: [429], delayMs: 1200 });
  assert("does not retry non-rate-limit Personal OS errors", notRetried.ok === false && notRetried.httpStatus === 500 && fetchCalls().length === 1);

  console.log("\nPersonal OS preload bridge:");
  const start = src.indexOf("// Personal OS cockpit");
  const end = src.indexOf("  visionAnalyze", start);
  const personalOsSection = src.slice(start, end > start ? end : undefined);
  assert("defines Personal OS section", start >= 0 && personalOsSection.length > 1000);
  const jsonHelperCount = (personalOsSection.match(/personalOsJson\(r,/g) || []).length;
  const retryHelperCount = (personalOsSection.match(/personalOsFetchJsonWithRetry\(/g) || []).length;
  assert("routes Personal OS responses through helpers", jsonHelperCount + retryHelperCount >= 13, `json=${jsonHelperCount} retry=${retryHelperCount}`);
  assert("does not directly parse Personal OS responses with r.json", !personalOsSection.includes("return r.json();"));
  assert("status offline fallback is marked ok false", personalOsSection.includes('return { ok: false, status: "offline"'));
  assert("draft queue offline fallback includes direct error", personalOsSection.includes('error: "Personal OS nicht erreichbar", errors:'));
  assert("read-only cockpit endpoints retry transient rate limits", retryHelperCount >= 3 && personalOsSection.includes("personalOsStatus: async") && personalOsSection.includes("personalOsDiagnostics: async") && personalOsSection.includes("personalOsDrafts: async") && personalOsSection.includes("statuses: [429]") && personalOsSection.includes("attempts: 2"));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  if (failed > 0) process.exit(1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
