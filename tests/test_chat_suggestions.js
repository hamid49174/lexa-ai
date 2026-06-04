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
  ${extractFn(chatSrc, "chatSuggestionNormalizedText")}
  ${extractFn(chatSrc, "chatSuggestionSearchText")}
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
  "chat.suggNextLexaImprovement": "Next Lexa improvement",
  "chat.suggRunFocusedTests": "Run focused tests",
  "chat.suggCheckRisks": "Check risks",
  "chat.suggCheckAccessibility": "Check accessibility",
  "chat.suggMeasurePerformance": "Measure performance",
  "chat.suggReviewMemory": "Review memory",
  "chat.suggBuildContextPack": "Build context pack",
  "chat.suggPlanToolRun": "Plan tool run",
  "chat.suggCheckPermissions": "Check permissions",
  "chat.suggVerifyResult": "Verify result",
  "chat.suggShipChecklist": "Ship checklist",
  "chat.suggRunSmokeTests": "Run smoke tests",
  "chat.suggCheckRollback": "Check rollback",
  "chat.suggDryRunFirst": "Dry run first",
  "chat.suggCheckBackup": "Check backup",
  "chat.suggConfirmChanges": "Confirm changes",
  "chat.suggStartTriage": "Start triage",
  "chat.suggFindLogs": "Find logs",
  "chat.suggVerifyFix": "Verify fix",
  "chat.suggShowVerifiedChanges": "Show verified changes",
  "chat.suggShowNextSteps": "Show next steps",
  "chat.suggShowOpenRisks": "Show open risks",
  "chat.suggShowAssumptions": "Show assumptions",
  "chat.suggListMissingContext": "List missing context",
  "chat.suggAskClarifyingQuestions": "Ask clarifying questions",
  "chat.suggDefineAcceptanceCriteria": "Define acceptance criteria",
  "chat.suggListEdgeCases": "List edge cases",
  "chat.suggDefineMvp": "Define MVP",
  "chat.suggDefineRubric": "Define rubric",
  "chat.suggRunEval": "Run eval",
  "chat.suggCompareBaseline": "Compare baseline",
  "chat.suggExtractActionItems": "Extract action items",
  "chat.suggListDecisions": "List decisions",
  "chat.suggMakeBrief": "Make brief",
  "chat.suggCheckMath": "Check math",
  "chat.suggShowFormula": "Show formula",
  "chat.suggListAssumptions": "List assumptions",
  "chat.suggAdjustTone": "Adjust tone",
  "chat.suggAddCta": "Add CTA",
  "chat.suggMakeConcise": "Make concise",
  "chat.suggSimplify": "Simplify",
  "chat.suggShowExample": "Show example",
  "chat.suggQuizMe": "Quiz me",
  "chat.suggVerifyAnswer": "Verify answer",
  "chat.suggFindSources": "Find sources",
  "chat.suggExtractClaims": "Extract claims",
  "chat.suggCompareOptions": "Compare options",
  "chat.suggMakeRecommendation": "Make recommendation",
  "chat.suggListOpenQuestions": "List open questions",
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

const lexaImprovementSuggestions = generateSuggestions(
  "Erledigt: Lexa ist robuster, die Antwortqualitaet ist besser und Tests sind gruen.",
  "will lexa intilegnz futeres autoamtion verbessern"
);
assert(
  "lexa improvement answers get focused next-step chips even with typo-heavy prompts",
  lexaImprovementSuggestions.join("|") === "Next Lexa improvement|Run focused tests|Check risks",
  JSON.stringify(lexaImprovementSuggestions)
);

const lexaImproveImperativeSuggestions = generateSuggestions(
  "",
  "Verbessere Lexa Chat-Intelligenz, Features und allgemeine Funktionen."
);
assert(
  "lexa improvement suggestions match German imperative wording",
  lexaImproveImperativeSuggestions.join("|") === "Next Lexa improvement|Run focused tests|Check risks",
  JSON.stringify(lexaImproveImperativeSuggestions)
);

const lexaReliabilitySuggestions = generateSuggestions(
  "",
  "Lexa reliability, stability und Robustheit verbessern."
);
assert(
  "lexa improvement suggestions match reliability and robustness wording",
  lexaReliabilitySuggestions.join("|") === "Next Lexa improvement|Run focused tests|Check risks",
  JSON.stringify(lexaReliabilitySuggestions)
);

const lexaAccessibilitySuggestions = generateSuggestions(
  "",
  "Lexa Barrierefreiheit, Bedienbarkeit und a11y verbessern."
);
assert(
  "lexa improvement suggestions match accessibility and usability wording",
  lexaAccessibilitySuggestions.join("|") === "Check accessibility|Run focused tests|List open questions",
  JSON.stringify(lexaAccessibilitySuggestions)
);

const lexaPerformanceSuggestions = generateSuggestions(
  "",
  "Lexa speed, latency, Ladezeit und Reaktionszeit verbessern."
);
assert(
  "lexa improvement suggestions match performance and latency wording",
  lexaPerformanceSuggestions.join("|") === "Measure performance|Run focused tests|Check risks",
  JSON.stringify(lexaPerformanceSuggestions)
);

const lexaMemoryContextSuggestions = generateSuggestions(
  "",
  "Lexa Memory, Kontext und Personalisierung verbessern."
);
assert(
  "lexa improvement suggestions match memory context and personalization wording",
  lexaMemoryContextSuggestions.join("|") === "Next Lexa improvement|Run focused tests|Check risks",
  JSON.stringify(lexaMemoryContextSuggestions)
);

const memoryReviewSuggestions = generateSuggestions(
  "",
  "Memory review for Lexa chat: what should stay stable vs draft?"
);
assert(
  "memory review requests get memory follow-up chips",
  memoryReviewSuggestions.join("|") === "Review memory|Build context pack|List open questions",
  JSON.stringify(memoryReviewSuggestions)
);

const contextPackSuggestions = generateSuggestions(
  "",
  "Build a context pack for Lexa project decisions and tasks."
);
assert(
  "context-pack requests get memory follow-up chips",
  contextPackSuggestions.join("|") === "Review memory|Build context pack|List open questions",
  JSON.stringify(contextPackSuggestions)
);

const memoryDefinitionSuggestions = generateSuggestions(
  "",
  "What is memory?"
);
assert(
  "simple memory definition questions do not get memory chips",
  memoryDefinitionSuggestions.length === 0,
  JSON.stringify(memoryDefinitionSuggestions)
);

const contextPackDefinitionSuggestions = generateSuggestions(
  "",
  "What is a context pack?"
);
assert(
  "simple context-pack definition questions do not get memory chips",
  contextPackDefinitionSuggestions.length === 0,
  JSON.stringify(contextPackDefinitionSuggestions)
);

const agentDefinitionSuggestions = generateSuggestions(
  "",
  "What is an agent?"
);
assert(
  "simple agent definition questions do not get tool chips",
  agentDefinitionSuggestions.length === 0,
  JSON.stringify(agentDefinitionSuggestions)
);

const toolWorkflowDefinitionSuggestions = generateSuggestions(
  "",
  "What is a tool workflow?"
);
assert(
  "simple tool-workflow definition questions do not get tool chips",
  toolWorkflowDefinitionSuggestions.length === 0,
  JSON.stringify(toolWorkflowDefinitionSuggestions)
);

const releaseReadinessDefinitionSuggestions = generateSuggestions(
  "",
  "What is release readiness?"
);
assert(
  "simple release-readiness definition questions do not get ship chips",
  releaseReadinessDefinitionSuggestions.length === 0,
  JSON.stringify(releaseReadinessDefinitionSuggestions)
);

const shipCheckDefinitionSuggestions = generateSuggestions(
  "",
  "What is a ship check?"
);
assert(
  "simple ship-check definition questions do not get ship chips",
  shipCheckDefinitionSuggestions.length === 0,
  JSON.stringify(shipCheckDefinitionSuggestions)
);

const backupDefinitionSuggestionsForDataSafety = generateSuggestions(
  "",
  "What is a backup?"
);
assert(
  "simple backup definition questions do not get data-safety chips",
  backupDefinitionSuggestionsForDataSafety.length === 0,
  JSON.stringify(backupDefinitionSuggestionsForDataSafety)
);

const dataLossDefinitionSuggestions = generateSuggestions(
  "",
  "What is data loss risk?"
);
assert(
  "simple data-loss definition questions do not get data-safety chips",
  dataLossDefinitionSuggestions.length === 0,
  JSON.stringify(dataLossDefinitionSuggestions)
);

const debuggingDefinitionSuggestions = generateSuggestions(
  "",
  "What is debugging?"
);
assert(
  "simple debugging definition questions do not get triage chips",
  debuggingDefinitionSuggestions.length === 0,
  JSON.stringify(debuggingDefinitionSuggestions)
);

const rootCauseDefinitionSuggestions = generateSuggestions(
  "",
  "What is root cause analysis?"
);
assert(
  "simple root-cause definition questions do not get triage chips",
  rootCauseDefinitionSuggestions.length === 0,
  JSON.stringify(rootCauseDefinitionSuggestions)
);

const statusUpdateDefinitionSuggestions = generateSuggestions(
  "",
  "What is a status update?"
);
assert(
  "simple status-update definition questions do not get status chips",
  statusUpdateDefinitionSuggestions.length === 0,
  JSON.stringify(statusUpdateDefinitionSuggestions)
);

const handoffDefinitionSuggestions = generateSuggestions(
  "",
  "What is a handoff?"
);
assert(
  "simple handoff definition questions do not get status chips",
  handoffDefinitionSuggestions.length === 0,
  JSON.stringify(handoffDefinitionSuggestions)
);

const clarificationDefinitionSuggestions = generateSuggestions(
  "",
  "What is a clarifying question?"
);
assert(
  "simple clarification definition questions do not get assumption chips",
  clarificationDefinitionSuggestions.length === 0,
  JSON.stringify(clarificationDefinitionSuggestions)
);

const assumptionDefinitionSuggestions = generateSuggestions(
  "",
  "What is an assumption?"
);
assert(
  "simple assumption definition questions do not get assumption chips",
  assumptionDefinitionSuggestions.length === 0,
  JSON.stringify(assumptionDefinitionSuggestions)
);

const prdDefinitionSuggestions = generateSuggestions(
  "",
  "What is a PRD?"
);
assert(
  "simple PRD definition questions do not get spec chips",
  prdDefinitionSuggestions.length === 0,
  JSON.stringify(prdDefinitionSuggestions)
);

const userStoryDefinitionSuggestions = generateSuggestions(
  "",
  "What is a user story?"
);
assert(
  "simple user-story definition questions do not get spec chips",
  userStoryDefinitionSuggestions.length === 0,
  JSON.stringify(userStoryDefinitionSuggestions)
);

const rubricDefinitionSuggestions = generateSuggestions(
  "",
  "What is a rubric?"
);
assert(
  "simple rubric definition questions do not get benchmark chips",
  rubricDefinitionSuggestions.length === 0,
  JSON.stringify(rubricDefinitionSuggestions)
);

const evalDefinitionSuggestions = generateSuggestions(
  "",
  "What is an eval?"
);
assert(
  "simple eval definition questions do not get benchmark chips",
  evalDefinitionSuggestions.length === 0,
  JSON.stringify(evalDefinitionSuggestions)
);

const meetingMinutesDefinitionSuggestions = generateSuggestions(
  "",
  "What are meeting minutes?"
);
assert(
  "simple meeting-minutes definition questions do not get summary chips",
  meetingMinutesDefinitionSuggestions.length === 0,
  JSON.stringify(meetingMinutesDefinitionSuggestions)
);

const actionItemsDefinitionSuggestions = generateSuggestions(
  "",
  "What are action items?"
);
assert(
  "simple action-item definition questions do not get summary chips",
  actionItemsDefinitionSuggestions.length === 0,
  JSON.stringify(actionItemsDefinitionSuggestions)
);

const percentageDefinitionSuggestions = generateSuggestions(
  "",
  "What is a percentage?"
);
assert(
  "simple percentage definition questions do not get numeric chips",
  percentageDefinitionSuggestions.length === 0,
  JSON.stringify(percentageDefinitionSuggestions)
);

const roiDefinitionSuggestions = generateSuggestions(
  "",
  "What is ROI?"
);
assert(
  "simple ROI definition questions do not get numeric chips",
  roiDefinitionSuggestions.length === 0,
  JSON.stringify(roiDefinitionSuggestions)
);

const ctaDefinitionSuggestions = generateSuggestions(
  "",
  "What is a CTA?"
);
assert(
  "simple CTA definition questions do not get communication chips",
  ctaDefinitionSuggestions.length === 0,
  JSON.stringify(ctaDefinitionSuggestions)
);

const emailDefinitionSuggestions = generateSuggestions(
  "",
  "What is an email?"
);
assert(
  "simple email definition questions do not get communication chips",
  emailDefinitionSuggestions.length === 0,
  JSON.stringify(emailDefinitionSuggestions)
);

const tutorialDefinitionSuggestions = generateSuggestions(
  "",
  "What is a tutorial?"
);
assert(
  "simple tutorial definition questions do not get learning chips",
  tutorialDefinitionSuggestions.length === 0,
  JSON.stringify(tutorialDefinitionSuggestions)
);

const exampleDefinitionSuggestions = generateSuggestions(
  "",
  "What is an example?"
);
assert(
  "simple example definition questions do not get learning chips",
  exampleDefinitionSuggestions.length === 0,
  JSON.stringify(exampleDefinitionSuggestions)
);

const lexaConversationSuggestions = generateSuggestions(
  "",
  "Lexa conversation flow, follow-up questions und Intent-Erkennung verbessern."
);
assert(
  "lexa improvement suggestions match conversation intelligence wording",
  lexaConversationSuggestions.join("|") === "Next Lexa improvement|Run focused tests|Check risks",
  JSON.stringify(lexaConversationSuggestions)
);

const lexaDevelopmentSuggestions = generateSuggestions(
  "",
  "Ziel: Lexa weiterentwickeln."
);
assert(
  "lexa improvement suggestions match German development wording",
  lexaDevelopmentSuggestions.join("|") === "Next Lexa improvement|Run focused tests|Check risks",
  JSON.stringify(lexaDevelopmentSuggestions)
);

const lexaExpandSuggestions = generateSuggestions(
  "",
  "Ziel: Lexa ausbauen."
);
assert(
  "lexa improvement suggestions match German expansion wording",
  lexaExpandSuggestions.join("|") === "Next Lexa improvement|Run focused tests|Check risks",
  JSON.stringify(lexaExpandSuggestions)
);

const assistantQualityDefinitionSuggestions = generateSuggestions(
  "",
  "what is assistant accessibility?"
);
assert(
  "simple assistant product definition questions do not get improvement chips",
  assistantQualityDefinitionSuggestions.length === 0,
  JSON.stringify(assistantQualityDefinitionSuggestions)
);

const lexaUmlautSuggestions = generateSuggestions(
  "Lexa Antwortqualität und Automatisierung verbessert.",
  ""
);
assert(
  "lexa improvement suggestions normalize German umlauts",
  lexaUmlautSuggestions[0] === "Next Lexa improvement",
  JSON.stringify(lexaUmlautSuggestions)
);

const sourceQualitySuggestions = generateSuggestions(
  "Ich habe drei Claims markiert: zwei sind belegt, eine Quelle fehlt und muss verifiziert werden.",
  ""
);
assert(
  "source-backed answer quality contexts get verification follow-up chips",
  sourceQualitySuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(sourceQualitySuggestions)
);

const simpleSourceDefinitionSuggestions = generateSuggestions(
  "",
  "was ist eine Quelle?"
);
assert(
  "simple source definition questions do not get verification chips",
  simpleSourceDefinitionSuggestions.length === 0,
  JSON.stringify(simpleSourceDefinitionSuggestions)
);

const simpleFactcheckDefinitionSuggestions = generateSuggestions(
  "",
  "Was ist ein Faktencheck?"
);
assert(
  "simple fact-check definition questions do not get verification chips",
  simpleFactcheckDefinitionSuggestions.length === 0,
  JSON.stringify(simpleFactcheckDefinitionSuggestions)
);

const directAnswerVerificationSuggestions = generateSuggestions(
  "",
  "Verify this answer."
);
assert(
  "direct answer verification requests get verification chips",
  directAnswerVerificationSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(directAnswerVerificationSuggestions)
);

const doubleCheckAnswerSuggestions = generateSuggestions(
  "",
  "Double-check my answer."
);
assert(
  "double-check answer requests get verification chips",
  doubleCheckAnswerSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(doubleCheckAnswerSuggestions)
);

const directClaimVerificationSuggestions = generateSuggestions(
  "",
  "Prüf diese Aussage."
);
assert(
  "direct claim verification requests get verification chips",
  directClaimVerificationSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(directClaimVerificationSuggestions)
);

const directStatementVerificationSuggestions = generateSuggestions(
  "",
  "Verify this statement."
);
assert(
  "direct statement verification requests get verification chips",
  directStatementVerificationSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(directStatementVerificationSuggestions)
);

const germanDirectAnswerVerificationSuggestions = generateSuggestions(
  "",
  "Prüf die Antwort."
);
assert(
  "German direct answer verification requests get verification chips",
  germanDirectAnswerVerificationSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(germanDirectAnswerVerificationSuggestions)
);

const germanPersonalAnswerVerificationSuggestions = generateSuggestions(
  "",
  "Prüf meine Antwort."
);
assert(
  "German personal answer verification requests get verification chips",
  germanPersonalAnswerVerificationSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(germanPersonalAnswerVerificationSuggestions)
);

const germanFactcheckAnswerSuggestions = generateSuggestions(
  "",
  "Faktencheck meine Antwort."
);
assert(
  "German fact-check answer requests get verification chips",
  germanFactcheckAnswerSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(germanFactcheckAnswerSuggestions)
);

const sourceSeparatorSuggestions = generateSuggestions(
  "This source-backed brief includes a fact-check table and unsupported-claims notes.",
  ""
);
assert(
  "source verification suggestions match hyphenated quality phrases",
  sourceSeparatorSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(sourceSeparatorSuggestions)
);

const sourceInflectionSuggestions = generateSuggestions(
  "",
  "Bitte verifiziere die Quellen und Belege."
);
assert(
  "source verification suggestions match German inflected verification verbs",
  sourceInflectionSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(sourceInflectionSuggestions)
);

const sourceValidationSuggestions = generateSuggestions(
  "",
  "Bitte validiere die Quellen und cross-check die Belege."
);
assert(
  "source verification suggestions match validation and cross-check wording",
  sourceValidationSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(sourceValidationSuggestions)
);

const researchReferenceSuggestions = generateSuggestions(
  "",
  "Bitte validiere die Studien, Papers und Referenzen."
);
assert(
  "source verification suggestions match research reference wording",
  researchReferenceSuggestions.join("|") === "Verify answer|Find sources|Extract claims",
  JSON.stringify(researchReferenceSuggestions)
);

const decisionBriefSuggestions = generateSuggestions(
  "",
  "Erstelle einen Entscheidungsbrief mit Optionen und Risiken fuer Lexa."
);
assert(
  "decision brief requests get decision follow-up chips",
  decisionBriefSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(decisionBriefSuggestions)
);

const strategyTradeoffSuggestions = generateSuggestions(
  "",
  "Soll ich fuer Lexa Performance oder Memory zuerst priorisieren? Vergleiche Optionen, Risiken und naechste Schritte."
);
assert(
  "strategy tradeoff questions get decision follow-up chips",
  strategyTradeoffSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(strategyTradeoffSuggestions)
);

const naturalDecisionComparisonSuggestions = generateSuggestions(
  "",
  "Soll ich Lexa Performance oder Memory zuerst verbessern?"
);
assert(
  "natural should-I comparison questions get decision follow-up chips",
  naturalDecisionComparisonSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(naturalDecisionComparisonSuggestions)
);

const naturalBetterComparisonSuggestions = generateSuggestions(
  "",
  "Was ist besser fuer Lexa: Performance oder Memory?"
);
assert(
  "natural better comparison questions get decision follow-up chips",
  naturalBetterComparisonSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(naturalBetterComparisonSuggestions)
);

const optionChoiceFollowupSuggestions = generateSuggestions(
  "",
  "Welche Option ist besser?"
);
assert(
  "option choice follow-ups get decision follow-up chips",
  optionChoiceFollowupSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(optionChoiceFollowupSuggestions)
);

const helpMeDecideSuggestions = generateSuggestions(
  "",
  "Hilf mir entscheiden."
);
assert(
  "help-me-decide requests get decision follow-up chips",
  helpMeDecideSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(helpMeDecideSuggestions)
);

const makeTheCallSuggestions = generateSuggestions(
  "",
  "Make the call."
);
assert(
  "make-the-call requests get decision follow-up chips",
  makeTheCallSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(makeTheCallSuggestions)
);

const whichOptionPickSuggestions = generateSuggestions(
  "",
  "Which option should I pick?"
);
assert(
  "which-option-pick follow-ups get decision chips",
  whichOptionPickSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(whichOptionPickSuggestions)
);

const rankOptionsSuggestions = generateSuggestions(
  "",
  "Rank these options: Performance, Memory, UX."
);
assert(
  "rank-options requests get decision follow-up chips",
  rankOptionsSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(rankOptionsSuggestions)
);

const prioritizeChoicesSuggestions = generateSuggestions(
  "",
  "Prioritize these choices: speed, memory, UX."
);
assert(
  "prioritize-choices requests get decision follow-up chips",
  prioritizeChoicesSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(prioritizeChoicesSuggestions)
);

const prosConsSuggestions = generateSuggestions(
  "",
  "Give me pros and cons of improving Lexa memory."
);
assert(
  "pros-and-cons requests get decision follow-up chips",
  prosConsSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(prosConsSuggestions)
);

const tradeoffsBetweenSuggestions = generateSuggestions(
  "",
  "Tradeoffs between Lexa Performance and Memory."
);
assert(
  "tradeoffs-between requests get decision follow-up chips",
  tradeoffsBetweenSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(tradeoffsBetweenSuggestions)
);

const decisionMatrixSuggestions = generateSuggestions(
  "",
  "Create a decision matrix for options: Performance, Memory, UX."
);
assert(
  "decision-matrix requests get decision follow-up chips",
  decisionMatrixSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(decisionMatrixSuggestions)
);

const criteriaScoringSuggestions = generateSuggestions(
  "",
  "Bewerte die Optionen nach Kriterien: Performance, Memory, UX."
);
assert(
  "criteria-scoring requests get decision follow-up chips",
  criteriaScoringSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(criteriaScoringSuggestions)
);

const roadmapMilestonesSuggestions = generateSuggestions(
  "",
  "Erstelle eine Roadmap fuer Lexa mit Meilensteinen und Timeline."
);
assert(
  "roadmap milestone requests get decision follow-up chips",
  roadmapMilestonesSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(roadmapMilestonesSuggestions)
);

const executionPlanPhasesSuggestions = generateSuggestions(
  "",
  "Create an execution plan with phases and owners for Lexa memory."
);
assert(
  "execution-plan phase requests get decision follow-up chips",
  executionPlanPhasesSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(executionPlanPhasesSuggestions)
);

const deadlineBudgetPlanSuggestions = generateSuggestions(
  "",
  "Plane Lexa Memory mit Deadline Freitag und 2 Stunden Budget."
);
assert(
  "deadline-budget planning requests get decision follow-up chips",
  deadlineBudgetPlanSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(deadlineBudgetPlanSuggestions)
);

const limitedRolloutPlanSuggestions = generateSuggestions(
  "",
  "Create a rollout plan for Lexa voice with limited resources."
);
assert(
  "limited-resource rollout plans get decision follow-up chips",
  limitedRolloutPlanSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(limitedRolloutPlanSuggestions)
);

const releaseRiskAssessmentSuggestions = generateSuggestions(
  "",
  "Create a risk assessment for Lexa release."
);
assert(
  "release risk assessment requests get risk-focused follow-up chips",
  releaseRiskAssessmentSuggestions.join("|") === "Check risks|Make recommendation|List open questions",
  JSON.stringify(releaseRiskAssessmentSuggestions)
);

const shipCheckSuggestions = generateSuggestions(
  "",
  "Run a production Ship Check for Lexa before publish with launch blockers."
);
assert(
  "ship-check requests get release-focused follow-up chips",
  shipCheckSuggestions.join("|") === "Ship checklist|Run smoke tests|Check rollback",
  JSON.stringify(shipCheckSuggestions)
);

const releaseReadinessSuggestions = generateSuggestions(
  "",
  "Check Lexa release readiness: tests, rollback, docs, security."
);
assert(
  "release-readiness requests get release-focused follow-up chips",
  releaseReadinessSuggestions.join("|") === "Ship checklist|Run smoke tests|Check rollback",
  JSON.stringify(releaseReadinessSuggestions)
);

const destructiveMemoryCleanupSuggestions = generateSuggestions(
  "",
  "Delete old memories for Lexa after backup and dry run."
);
assert(
  "destructive memory-cleanup requests get data-safety follow-up chips",
  destructiveMemoryCleanupSuggestions.join("|") === "Dry run first|Check backup|Confirm changes",
  JSON.stringify(destructiveMemoryCleanupSuggestions)
);

const backupRestoreSuggestions = generateSuggestions(
  "",
  "Restore backup for Lexa database after migration."
);
assert(
  "backup-restore requests get data-safety follow-up chips",
  backupRestoreSuggestions.join("|") === "Dry run first|Check backup|Confirm changes",
  JSON.stringify(backupRestoreSuggestions)
);

const debugTriageSuggestions = generateSuggestions(
  "",
  "Debug Lexa startup error: collect logs, reproduce, find root cause."
);
assert(
  "debug-triage requests get debugging follow-up chips",
  debugTriageSuggestions.join("|") === "Start triage|Find logs|Verify fix",
  JSON.stringify(debugTriageSuggestions)
);

const incidentTriageSuggestions = generateSuggestions(
  "",
  "Incident triage for Lexa chat outage with logs and rollback."
);
assert(
  "incident-triage requests get debugging follow-up chips",
  incidentTriageSuggestions.join("|") === "Start triage|Find logs|Verify fix",
  JSON.stringify(incidentTriageSuggestions)
);

const statusHandoffSuggestions = generateSuggestions(
  "",
  "Wie weit sind wir mit Lexa? Zeig erledigt, verifiziert und offen."
);
assert(
  "status-handoff requests get status follow-up chips",
  statusHandoffSuggestions.join("|") === "Show verified changes|Show next steps|Show open risks",
  JSON.stringify(statusHandoffSuggestions)
);

const handoffSummarySuggestions = generateSuggestions(
  "",
  "Create a handoff summary for Lexa project changes, tests, next steps, and risks."
);
assert(
  "handoff-summary requests get status follow-up chips",
  handoffSummarySuggestions.join("|") === "Show verified changes|Show next steps|Show open risks",
  JSON.stringify(handoffSummarySuggestions)
);

const clarificationSuggestions = generateSuggestions(
  "",
  "Before building this Lexa feature, ask clarifying questions and state assumptions."
);
assert(
  "clarification requests get assumption follow-up chips",
  clarificationSuggestions.join("|") === "Show assumptions|List missing context|Ask clarifying questions",
  JSON.stringify(clarificationSuggestions)
);

const missingContextSuggestions = generateSuggestions(
  "",
  "List missing context for this Lexa implementation plan before proceeding."
);
assert(
  "missing-context requests get assumption follow-up chips",
  missingContextSuggestions.join("|") === "Show assumptions|List missing context|Ask clarifying questions",
  JSON.stringify(missingContextSuggestions)
);

const featureSpecSuggestions = generateSuggestions(
  "",
  "Draft a feature spec for Lexa voice memory with user stories and edge cases."
);
assert(
  "feature-spec requests get spec follow-up chips",
  featureSpecSuggestions.join("|") === "Define acceptance criteria|List edge cases|Define MVP",
  JSON.stringify(featureSpecSuggestions)
);

const prdSuggestions = generateSuggestions(
  "",
  "Create a PRD for Lexa agent handoff with success metrics and non-goals."
);
assert(
  "prd requests get spec follow-up chips",
  prdSuggestions.join("|") === "Define acceptance criteria|List edge cases|Define MVP",
  JSON.stringify(prdSuggestions)
);

const evalRubricSuggestions = generateSuggestions(
  "",
  "Create an answer quality eval rubric for Lexa vs GPT, Claude, and Gemini."
);
assert(
  "eval-rubric requests get benchmark follow-up chips",
  evalRubricSuggestions.join("|") === "Define rubric|Run eval|Compare baseline",
  JSON.stringify(evalRubricSuggestions)
);

const assistantBenchmarkSuggestions = generateSuggestions(
  "",
  "Benchmark Lexa assistant answers with a golden set and hallucination eval."
);
assert(
  "assistant-benchmark requests get benchmark follow-up chips",
  assistantBenchmarkSuggestions.join("|") === "Define rubric|Run eval|Compare baseline",
  JSON.stringify(assistantBenchmarkSuggestions)
);

const meetingSummarySuggestions = generateSuggestions(
  "",
  "Summarize meeting notes for Lexa: extract action items, owners, deadlines, and decisions."
);
assert(
  "meeting-summary requests get summary follow-up chips",
  meetingSummarySuggestions.join("|") === "Extract action items|List decisions|Make brief",
  JSON.stringify(meetingSummarySuggestions)
);

const transcriptActionSuggestions = generateSuggestions(
  "",
  "Turn transcript into action items for Lexa planning with open questions."
);
assert(
  "transcript-action requests get summary follow-up chips",
  transcriptActionSuggestions.join("|") === "Extract action items|List decisions|Make brief",
  JSON.stringify(transcriptActionSuggestions)
);

const monthlyCostSuggestions = generateSuggestions(
  "",
  "Calculate monthly cost: 120000 tokens per day at 0.15 USD per 1M tokens."
);
assert(
  "monthly-cost calculations get numeric follow-up chips",
  monthlyCostSuggestions.join("|") === "Check math|Show formula|List assumptions",
  JSON.stringify(monthlyCostSuggestions)
);

const percentChangeSuggestions = generateSuggestions(
  "",
  "Berechne prozentuale Aenderung von 80 auf 92 Nutzern."
);
assert(
  "percentage-change calculations get numeric follow-up chips",
  percentChangeSuggestions.join("|") === "Check math|Show formula|List assumptions",
  JSON.stringify(percentChangeSuggestions)
);

const customerEmailDraftSuggestions = generateSuggestions(
  "",
  "Draft a customer email reply about the Lexa refund delay with a warm tone and clear CTA."
);
assert(
  "customer-email drafts get communication follow-up chips",
  customerEmailDraftSuggestions.join("|") === "Adjust tone|Add CTA|Make concise",
  JSON.stringify(customerEmailDraftSuggestions)
);

const germanAnnouncementDraftSuggestions = generateSuggestions(
  "",
  "Schreibe eine Ankuendigung an das Lexa Team mit Betreff, kurzem Ton und naechstem Schritt."
);
assert(
  "German announcement drafts get communication follow-up chips",
  germanAnnouncementDraftSuggestions.join("|") === "Adjust tone|Add CTA|Make concise",
  JSON.stringify(germanAnnouncementDraftSuggestions)
);

const lexaArchitectureLearningSuggestions = generateSuggestions(
  "",
  "Teach me Lexa architecture step by step with examples and a quick check."
);
assert(
  "step-by-step learning requests get teaching follow-up chips",
  lexaArchitectureLearningSuggestions.join("|") === "Simplify|Show example|Quiz me",
  JSON.stringify(lexaArchitectureLearningSuggestions)
);

const beginnerApiLearningSuggestions = generateSuggestions(
  "",
  "Explain async API workflows for beginners with examples and common mistakes."
);
assert(
  "beginner explanation requests get teaching follow-up chips",
  beginnerApiLearningSuggestions.join("|") === "Simplify|Show example|Quiz me",
  JSON.stringify(beginnerApiLearningSuggestions)
);

const rollbackPlanSuggestions = generateSuggestions(
  "",
  "Rollback plan for Lexa voice launch."
);
assert(
  "rollback-plan requests get risk-focused follow-up chips",
  rollbackPlanSuggestions.join("|") === "Check risks|Make recommendation|List open questions",
  JSON.stringify(rollbackPlanSuggestions)
);

const threatModelSuggestions = generateSuggestions(
  "",
  "Create a threat model for Lexa memory tools."
);
assert(
  "threat-model requests get risk-focused follow-up chips",
  threatModelSuggestions.join("|") === "Check risks|Make recommendation|List open questions",
  JSON.stringify(threatModelSuggestions)
);

const privacyReviewSuggestions = generateSuggestions(
  "",
  "Privacy review for Lexa agent permissions."
);
assert(
  "privacy-review requests get risk-focused follow-up chips",
  privacyReviewSuggestions.join("|") === "Check risks|Make recommendation|List open questions",
  JSON.stringify(privacyReviewSuggestions)
);

const accessibilityReviewSuggestions = generateSuggestions(
  "",
  "Accessibility review for Lexa chat keyboard navigation and screen reader labels."
);
assert(
  "accessibility-review requests get accessibility-focused follow-up chips",
  accessibilityReviewSuggestions.join("|") === "Check accessibility|Run focused tests|List open questions",
  JSON.stringify(accessibilityReviewSuggestions)
);

const contrastAuditSuggestions = generateSuggestions(
  "",
  "Check contrast and focus order for Lexa settings UI."
);
assert(
  "contrast/focus-order requests get accessibility-focused follow-up chips",
  contrastAuditSuggestions.join("|") === "Check accessibility|Run focused tests|List open questions",
  JSON.stringify(contrastAuditSuggestions)
);

const performanceReviewSuggestions = generateSuggestions(
  "",
  "Performance review for Lexa chat latency and startup time."
);
assert(
  "performance-review requests get performance-focused follow-up chips",
  performanceReviewSuggestions.join("|") === "Measure performance|Run focused tests|Check risks",
  JSON.stringify(performanceReviewSuggestions)
);

const latencyBudgetSuggestions = generateSuggestions(
  "",
  "Create a latency budget for Lexa streaming."
);
assert(
  "latency-budget requests get performance-focused follow-up chips",
  latencyBudgetSuggestions.join("|") === "Measure performance|Run focused tests|Check risks",
  JSON.stringify(latencyBudgetSuggestions)
);

const testPlanSuggestions = generateSuggestions(
  "",
  "Create a test plan for Lexa release with acceptance criteria."
);
assert(
  "test-plan requests get test-focused follow-up chips",
  testPlanSuggestions.join("|") === "Run focused tests|Check risks|List open questions",
  JSON.stringify(testPlanSuggestions)
);

const regressionTestPlanSuggestions = generateSuggestions(
  "",
  "Regression test plan for Lexa streaming workflow."
);
assert(
  "regression-test-plan requests get test-focused follow-up chips",
  regressionTestPlanSuggestions.join("|") === "Run focused tests|Check risks|List open questions",
  JSON.stringify(regressionTestPlanSuggestions)
);

const toolExecutionPlanSuggestions = generateSuggestions(
  "",
  "Create a tool execution plan for Lexa workspace automation with permissions and rollback."
);
assert(
  "tool-execution plan requests get tool-focused follow-up chips",
  toolExecutionPlanSuggestions.join("|") === "Plan tool run|Check permissions|Verify result",
  JSON.stringify(toolExecutionPlanSuggestions)
);

const agentRunSuggestions = generateSuggestions(
  "",
  "Plan an agent run for Lexa repository cleanup and verification."
);
assert(
  "agent-run requests get tool-focused follow-up chips",
  agentRunSuggestions.join("|") === "Plan tool run|Check permissions|Verify result",
  JSON.stringify(agentRunSuggestions)
);

const plainCompareVsSuggestions = generateSuggestions(
  "",
  "Vergleiche Lexa Performance vs Memory."
);
assert(
  "plain compare-vs questions get decision follow-up chips",
  plainCompareVsSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(plainCompareVsSuggestions)
);

const whatWouldYouDoComparisonSuggestions = generateSuggestions(
  "",
  "Was wuerdest du machen: Performance oder Memory?"
);
assert(
  "what-would-you-do comparison questions get decision follow-up chips",
  whatWouldYouDoComparisonSuggestions.join("|") === "Compare options|Make recommendation|List open questions",
  JSON.stringify(whatWouldYouDoComparisonSuggestions)
);

const simpleDecisionDefinitionSuggestions = generateSuggestions(
  "",
  "Was ist eine Entscheidung?"
);
assert(
  "simple decision definition questions do not get decision chips",
  simpleDecisionDefinitionSuggestions.length === 0,
  JSON.stringify(simpleDecisionDefinitionSuggestions)
);

const simpleRoadmapDefinitionSuggestions = generateSuggestions(
  "",
  "Was ist eine Roadmap?"
);
assert(
  "simple roadmap definition questions do not get decision chips",
  simpleRoadmapDefinitionSuggestions.length === 0,
  JSON.stringify(simpleRoadmapDefinitionSuggestions)
);

const simpleShouldIQuestionSuggestions = generateSuggestions(
  "",
  "Soll ich Wasser trinken?"
);
assert(
  "simple should-I questions without comparison stay light",
  simpleShouldIQuestionSuggestions.length === 0,
  JSON.stringify(simpleShouldIQuestionSuggestions)
);

const vagueBetterQuestionSuggestions = generateSuggestions(
  "",
  "Was ist besser?"
);
assert(
  "vague better questions without options stay light",
  vagueBetterQuestionSuggestions.length === 0,
  JSON.stringify(vagueBetterQuestionSuggestions)
);

const simpleComparisonDefinitionSuggestions = generateSuggestions(
  "",
  "Was bedeutet Vergleich?"
);
assert(
  "simple comparison definition questions stay light",
  simpleComparisonDefinitionSuggestions.length === 0,
  JSON.stringify(simpleComparisonDefinitionSuggestions)
);

const plainSourceComparisonSuggestions = generateSuggestions(
  "",
  "Vergleiche die Quellen."
);
assert(
  "plain source comparison requests do not get decision chips",
  plainSourceComparisonSuggestions.length === 0,
  JSON.stringify(plainSourceComparisonSuggestions)
);

const vagueWhatWouldYouDoSuggestions = generateSuggestions(
  "",
  "Was wuerdest du machen?"
);
assert(
  "vague what-would-you-do questions stay light",
  vagueWhatWouldYouDoSuggestions.length === 0,
  JSON.stringify(vagueWhatWouldYouDoSuggestions)
);

const simpleRankingDefinitionSuggestions = generateSuggestions(
  "",
  "What is ranking?"
);
assert(
  "simple ranking definition questions stay light",
  simpleRankingDefinitionSuggestions.length === 0,
  JSON.stringify(simpleRankingDefinitionSuggestions)
);

const prosConsDefinitionSuggestions = generateSuggestions(
  "",
  "What does pros and cons mean?"
);
assert(
  "pros-and-cons definition questions stay light",
  prosConsDefinitionSuggestions.length === 0,
  JSON.stringify(prosConsDefinitionSuggestions)
);

const decisionMatrixDefinitionSuggestions = generateSuggestions(
  "",
  "What is a decision matrix?"
);
assert(
  "decision-matrix definition questions stay light",
  decisionMatrixDefinitionSuggestions.length === 0,
  JSON.stringify(decisionMatrixDefinitionSuggestions)
);

const executionPlanDefinitionSuggestions = generateSuggestions(
  "",
  "What is an execution plan?"
);
assert(
  "execution-plan definition questions stay light",
  executionPlanDefinitionSuggestions.length === 0,
  JSON.stringify(executionPlanDefinitionSuggestions)
);

const deadlineDefinitionSuggestions = generateSuggestions(
  "",
  "Was ist eine Deadline?"
);
assert(
  "deadline definition questions stay light",
  deadlineDefinitionSuggestions.length === 0,
  JSON.stringify(deadlineDefinitionSuggestions)
);

const budgetDefinitionSuggestions = generateSuggestions(
  "",
  "What is a budget?"
);
assert(
  "budget definition questions stay light",
  budgetDefinitionSuggestions.length === 0,
  JSON.stringify(budgetDefinitionSuggestions)
);

const riskAssessmentDefinitionSuggestions = generateSuggestions(
  "",
  "What is a risk assessment?"
);
assert(
  "risk-assessment definition questions stay light",
  riskAssessmentDefinitionSuggestions.length === 0,
  JSON.stringify(riskAssessmentDefinitionSuggestions)
);

const threatModelDefinitionSuggestions = generateSuggestions(
  "",
  "What is a threat model?"
);
assert(
  "threat-model definition questions stay light",
  threatModelDefinitionSuggestions.length === 0,
  JSON.stringify(threatModelDefinitionSuggestions)
);

const privacyReviewDefinitionSuggestions = generateSuggestions(
  "",
  "What is a privacy review?"
);
assert(
  "privacy-review definition questions stay light",
  privacyReviewDefinitionSuggestions.length === 0,
  JSON.stringify(privacyReviewDefinitionSuggestions)
);

const accessibilityDefinitionSuggestions = generateSuggestions(
  "",
  "What is accessibility?"
);
assert(
  "accessibility definition questions stay light",
  accessibilityDefinitionSuggestions.length === 0,
  JSON.stringify(accessibilityDefinitionSuggestions)
);

const screenReaderDefinitionSuggestions = generateSuggestions(
  "",
  "What is a screen reader?"
);
assert(
  "screen-reader definition questions stay light",
  screenReaderDefinitionSuggestions.length === 0,
  JSON.stringify(screenReaderDefinitionSuggestions)
);

const latencyDefinitionSuggestions = generateSuggestions(
  "",
  "What is latency?"
);
assert(
  "latency definition questions stay light",
  latencyDefinitionSuggestions.length === 0,
  JSON.stringify(latencyDefinitionSuggestions)
);

const profilingDefinitionSuggestions = generateSuggestions(
  "",
  "What is profiling?"
);
assert(
  "profiling definition questions stay light",
  profilingDefinitionSuggestions.length === 0,
  JSON.stringify(profilingDefinitionSuggestions)
);

const testPlanDefinitionSuggestions = generateSuggestions(
  "",
  "What is a test plan?"
);
assert(
  "test-plan definition questions stay light",
  testPlanDefinitionSuggestions.length === 0,
  JSON.stringify(testPlanDefinitionSuggestions)
);

const acceptanceCriteriaDefinitionSuggestions = generateSuggestions(
  "",
  "What are acceptance criteria?"
);
assert(
  "acceptance-criteria definition questions stay light",
  acceptanceCriteriaDefinitionSuggestions.length === 0,
  JSON.stringify(acceptanceCriteriaDefinitionSuggestions)
);

const lexaSeparatorSuggestions = generateSuggestions(
  "Lexa answer-quality and user-experience improvements are ready.",
  ""
);
assert(
  "lexa improvement suggestions match hyphenated product quality phrases",
  lexaSeparatorSuggestions.join("|") === "Next Lexa improvement|Run focused tests|Check risks",
  JSON.stringify(lexaSeparatorSuggestions)
);

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
