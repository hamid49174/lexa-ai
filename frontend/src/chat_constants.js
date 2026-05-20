/* Chat constants loaded before chat.js. Keep this file free of module syntax. */

// Multi-step signal words/patterns (German + English)
const _AGENT_PATTERNS = [
  // Sequential actions
  /\bund\s+(dann|danach|anschlie[sÃŸ]end)\b/i,
  /\bdanach\b/i,
  /\berstens\b.*\bzweitens\b/i,
  /\bschritt\s*\d/i,
  /\b(zuerst|erst)\b.*\b(dann|danach)\b/i,
  // Batch/bulk operations
  /\b(alle|saemtliche|jeden|jede|jedes)\b.*\b(und|dann|danach)\b/i,
  /\braeume?\s+(auf|auf\b|den|die|das|meinen?)/i,
  /\bsortiere?\b.*\bund\b/i,
  /\borganisiere?\b/i,
  /\bbereinige?\b/i,
  // Multi-target actions
  /\b(oeffne|starte|schliesse)\b.*\bund\b.*\b(oeffne|starte|schliesse)\b/i,
  // Analysis + action combos
  /\b(finde|suche|pruefe|check)\b.*\b(und|dann)\b.*\b(loesch|entfern|verschieb|kopier|erstell)/i,
  /\b(analysiere?|scanne?)\b.*\bund\b/i,
  /\b(research|recherche|recherchiere|quellenrecherche|quellenbasiert|source[-\s]?backed|deep research)\b/i,
  /\b(brief|bericht|report|analyse|analysis|uebersicht|overview)\b.*\b(quellen|sources|citations|belege|evidence)\b/i,
  /\b(quellen|sources|citations|belege|evidence)\b.*\b(brief|bericht|report|analyse|analysis|uebersicht|overview)\b/i,
  /\b(fakten|annahmen|evidenz|risiken)\b.*\b(naechste|next|schritte|aktionen)\b/i,
  /\b(workspace|arbeitsentwurf|arbeitsbereich|artifact|artefakt|canvas)\b.*\b(draft|entwurf|markdown|kontext|context)\b/i,
  /\b(draft|entwurf|markdown|kontext|context)\b.*\b(workspace|arbeitsentwurf|arbeitsbereich|artifact|artefakt|canvas)\b/i,
  /\b(context\s*pack|contextpack|kontextpaket|project\s*briefing|projektbriefing)\b/i,
  /\b(personal\s*os|os)\b.*\b(context|kontext|briefing|pack|paket)\b/i,
  /\b(context|kontext)\b.*\b(facts|fakten|assumptions|annahmen|decisions|entscheidungen|tasks|aufgaben)\b/i,
  /\b(review|reviewe|pruef|pruefe|ueberpruef|freigabe|approval)\b.*\b(draft|drafts|entwurf|entwuerfe|queue)\b/i,
  /\b(personal\s*os|os)\b.*\b(draft|drafts|entwurf|entwuerfe)\b.*\b(review|pruef|freigabe|approval)\b/i,
  /\b(baue|erstelle|entwirf|design|create|build|design)\b.*\b(lexa\s*)?(skill|skills|gem|gems|custom\s*assistant|custom\s*gpt|assistentenprofil|spezialist)\b/i,
  /\b(skill|skills|gem|gems|custom\s*assistant|custom\s*gpt|assistentenprofil|spezialist)\b.*\b(draft|entwurf|markdown|template|vorlage|instructions|anleitung)\b/i,
  /\b(deep\s*think|deepthink|extended\s*thinking|denk\s*tief|tiefer\s*denken|durchdenk|durchdenke|entscheidungsbrief)\b/i,
  /\b(decision|entscheidung|entscheiden|decide|abw[aÃ¤]g|abwaeg)\b.*\b(options?|optionen|alternativen|tradeoffs?|risiken?|risks?|pros?|cons?|pro|contra)\b/i,
  /\b(options?|optionen|alternativen|tradeoffs?|risiken?|risks?|pros?|cons?|pro|contra)\b.*\b(decision|entscheidung|entscheiden|decide|abw[aÃ¤]g|abwaeg)\b/i,
  /\b(ship|shipping|release|launch|publish|veroeffentlich|veroeffentlichen|produktreif|production[-\s]?ready)\b.*\b(check|audit|qa|test|tests|regression|readiness|freigabe|blocker)\b/i,
  /\b(check|audit|qa|test|tests|regression|readiness|freigabe|blocker)\b.*\b(ship|shipping|release|launch|publish|veroeffentlich|veroeffentlichen|produktreif|production[-\s]?ready)\b/i,
  // Backup + cleanup combos
  /\bbackup\b.*\bund\b/i,
  /\b(loesch|entfern)\b.*\bduplikat/i,
  // Explicit multi-step language
  /\bfuer\s+mich\b.*\b(alles|komplett|vollstaendig)\b/i,
  /\bmach\s+(alles|das\s+alles)\b/i,
  /kuemmere?\s+dich\s+um/i,
];
