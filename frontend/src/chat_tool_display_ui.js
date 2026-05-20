/*
 * Tool display helpers for classic renderer scripts.
 * Real tool execution and result rendering stay in chat.js.
 */

function toolResultDisplayText(data) {
  let resultText = "";
  const d = data;
  if (d && typeof d === "string") {
    resultText = d;
  } else if (d && typeof d === "object") {
    resultText = d.summary || d.message || d.error || "";
    if (!resultText) {
      const skip = new Set(["icon", "icon_code", "will_rain", "success"]);
      resultText = Object.entries(d).filter(([k, v]) => v && !skip.has(k)).map(([k, v]) => `${k}: ${v}`).join(". ");
    }
  }
  return resultText;
}
