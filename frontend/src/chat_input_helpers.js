/* Pure chat input helpers loaded before chat.js. Keep this file free of module syntax. */

function chatInputMetrics(value, config = LexaConfig) {
  const text = String(value || "");
  const max = Number(config?.MAX_CHAT_INPUT_LENGTH) || 4000;
  const warnAt = Number(config?.CHAR_COUNTER_WARN) || Math.floor(max * 0.75);
  const dangerAt = Math.min(Number(config?.CHAR_COUNTER_DANGER) || Math.floor(max * 0.95), max);
  const length = text.length;
  return {
    length,
    max,
    warn: length >= warnAt && length < dangerAt,
    danger: length >= dangerAt && length <= max,
    over: length > max,
    visible: length >= warnAt,
    label: `${length}/${max}`,
  };
}
