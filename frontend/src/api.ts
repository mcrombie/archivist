import { readNdjson } from "./delivery";

export type Project = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  settings: {
    ignore_existing_index: boolean;
    consult_existing_index: boolean;
  };
  source_files: string[];
  ignored_documents: string[];
  existing_index_documents: string[];
  stats: {
    source_files: number;
    chunks: number;
    searchable_chunks: number;
    existing_index_chunks: number;
  };
  embedded: boolean;
  embedded_chunks: number;
  is_builtin?: boolean;
};

export type DevelopmentSource = {
  source_number: number;
  citation_label: string;
  document: string;
  chapter_title: string;
  chunk_id: string;
  chunk_ids: string[];
  paragraph_start?: number;
  paragraph_end?: number;
  text: string;
};

export type PublicSource = {
  kind: "public_locator";
  source_number: number;
  citation_label: string;
  title: string;
  edition: {
    id: string;
    name: string;
    locator_kind: "page" | "location" | "section";
  };
  locator: {
    start: string;
    end: string;
    label: string;
  };
  excerpt?: string;
};

export type SourceReference = DevelopmentSource | PublicSource;
export type SourceChunk = DevelopmentSource;

export type DisplayGroup = {
  source_numbers: number[];
  text: string;
  citation_labels: string[];
};

export type ExposureProfile = "development" | "public_demo";

export type AppConfig = {
  exposure_profile: ExposureProfile;
  project: Project;
  features: {
    cost_ledger: boolean;
    full_source_text: boolean;
    local_tools: boolean;
    public_page_locators: boolean;
    full_context_answers?: boolean;
    progressive_answers?: boolean;
  };
};

export type AnswerStrategy = "rag" | "full_context";

export function answerPolicyLabel(version: string | null | undefined) {
  if (version === "retrieval-authored-v5") return "Retrieval-authored v5";
  if (version === "retrieval-authored-v4") return "Retrieval-authored v4";
  if (version === "retrieval-authored-v3") return "Retrieval-authored v3";
  if (version === "retrieval-authored-v2") return "Retrieval-authored v2";
  if (version === "retrieval-authored-v1") return "Retrieval-authored v1";
  if (version === "application-compiled-v1") return "Application-compiled v1";
  if (version === "evidence-planned-v26") return "Evidence-planned v26";
  if (version === "full-context-v2") return "Full-context v2";
  return version ? `Answer policy · ${version}` : null;
}

export const DEFAULT_ANSWER_STRATEGY: AnswerStrategy = "rag";

export type ProgressiveAnswerStage =
  | "accepted"
  | "checking_corpus"
  | "resolving_question"
  | "planning_search"
  | "retrieving_sources"
  | "checking_evidence"
  | "preparing_context"
  | "generating_answer"
  | "validating_answer"
  | "checking_release";

export type ProgressiveStageUpdate = {
  stage: ProgressiveAnswerStage;
  message: string;
};

export type ProgressiveHeartbeatUpdate = {
  count: number;
};

export type ProgressiveCheckedClaim = {
  claimIndex: number;
  paragraph: number;
  text: string;
};

export const PROGRESSIVE_STAGE_COPY = {
  accepted: "Starting your request.",
  checking_corpus: "Checking manuscript availability.",
  resolving_question: "Resolving conversation context.",
  planning_search: "Planning a source search.",
  retrieving_sources: "Retrieving manuscript evidence.",
  checking_evidence: "Checking evidence sufficiency.",
  preparing_context: "Preparing source context.",
  generating_answer: "Drafting an answer from retrieved evidence.",
  validating_answer: "Checking response structure and citation references.",
  checking_release: "Applying public release safeguards."
} satisfies Readonly<Record<ProgressiveAnswerStage, string>>;

// These client bounds match the broadest checked-claim generation contract:
// full-context answers permit up to 40 claims of 2,000 characters and 24,000
// total claim characters. Interpretive framing is never carried in these frames.
export const MAX_PROGRESSIVE_CLAIMS = 40;
export const MAX_PROGRESSIVE_PARAGRAPH = 40;
export const MAX_PROGRESSIVE_CLAIM_CHARACTERS = 2_000;
export const MAX_PROGRESSIVE_CLAIM_CHARACTERS_TOTAL = 24_000;

export type ConversationHistoryTurn = {
  question: string;
  answer: string;
  archivist_mode?: ArchivistModeId;
};

export type AnswerRunDiagnostics = {
  schema: "archivist.answer_run_diagnostics/3";
  cohort: {
    rag_policy_version: string;
    query_planner_prompt_version: string;
    coverage_prompt_version: string;
    normalizer_version: string;
    coverage_instructions_sha256: string;
    coverage_schema_sha256: string;
    generator_model: string;
    generator_reasoning_effort: string;
    generator_verbosity: string;
    answer_strategy?: AnswerStrategy;
    answer_strategy_version?: string;
  };
  answer_status: string;
  evidence_decision: string;
  validation_result: "valid" | "invalid" | "not_run";
  content_outcome: "valid_complete" | "valid_partial" | "insufficient_evidence" | null;
  validation_error_code: string | null;
  repair_applied: boolean;
  repair_codes: string[];
  planner:
    | {
        schema: "archivist.planner_call_diagnostics/1";
        status: "unknown" | "not_called" | "succeeded" | "failed";
        failure_code: string | null;
        exception_class: string | null;
        exception_code: string | null;
      }
    | {
        schema: "archivist.planner_call_diagnostics/2";
        status: "not_called" | "succeeded" | "failed";
        failure_code: string | null;
        planner_validation_code: string | null;
        exception_class: string | null;
        exception_code: string | null;
      };
  stage_timings_ms: Record<string, number>;
};

export type CostEvent = {
  operation: string;
  model: string;
  tokens: number;
  cost_usd: number | null;
  timestamp: string;
};

export type CostOperationBreakdown = {
  operation: string;
  calls: number;
  tokens: number;
  cost_usd: number;
};

export type CostSettings = {
  monthly_budget_usd: number | null;
  warning_threshold_percent: number;
  hard_limit_enabled: boolean;
};

export type CostSummary = {
  currency: "USD";
  pricing_version: string;
  accuracy: "estimated";
  tracking_started_at: string | null;
  turn_usd: number;
  conversation_usd: number;
  month_usd: number;
  all_time_usd: number;
  unpriced_events: number;
  budget: CostSettings & {
    percent_used: number | null;
    remaining_usd: number | null;
    warning: boolean;
    exceeded: boolean;
  };
  operations: CostOperationBreakdown[];
  recent_events: CostEvent[];
};

export type CandidateTerm = {
  term: string;
  count: number;
};

export type AnswerPerspective =
  | "neutral"
  | "triumphalist"
  | "tragic"
  | "pious"
  | "romantic";

export type HistoriographicalLens =
  | "evidence_first"
  | "triumphalist"
  | "tragic";

export type AnswerVoice =
  | "scholarly"
  | "plainspoken"
  | "romantic";

export type AnswerWorldview =
  | "none"
  | "pious"
  | "secular_humanist"
  | "enlightenment_rationalist";

export type AnswerFacets = {
  historiographicalLens: HistoriographicalLens;
  voice: AnswerVoice;
  worldview: AnswerWorldview;
};

export type ArchivistModeId =
  | "professional"
  | "essential"
  | "pretty_pink_princess"
  | "baleful_black_baron"
  | "ember_and_ink"
  | "forest"
  | "cromb_coo_coo"
  | "tidal_archivist"
  | "illuminated_codex"
  | "cosmic_almanac";

export const DEFAULT_ANSWER_FACETS: AnswerFacets = {
  historiographicalLens: "evidence_first",
  voice: "scholarly",
  worldview: "none"
};

export class ApiRequestError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
  }
}

export class ProgressiveUnavailableError extends ApiRequestError {
  readonly receivedStreamEvent = false;

  constructor(status: number, message: string, detail: unknown) {
    super(status, message, detail);
    this.name = "ProgressiveUnavailableError";
  }
}

export class ProgressiveStreamError extends Error {
  readonly receivedStreamEvent: boolean;
  readonly code?: string;

  constructor(message: string, receivedStreamEvent: boolean, code?: string) {
    super(message);
    this.name = "ProgressiveStreamError";
    this.receivedStreamEvent = receivedStreamEvent;
    this.code = code;
  }
}

function detailMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return fallback;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    const detail = data?.detail ?? response.statusText;
    throw new ApiRequestError(response.status, detailMessage(detail, response.statusText), detail);
  }

  return data as T;
}

export async function listProjects(): Promise<Project[]> {
  const data = await requestJson<{ projects: Project[] }>("/api/projects");
  return data.projects;
}

export async function getAppConfig(): Promise<AppConfig> {
  return requestJson<AppConfig>("/api/config");
}

export async function createProject(input: {
  projectName: string;
  ignoreExistingIndex: boolean;
  consultExistingIndex: boolean;
  files: FileList | File[];
}): Promise<Project> {
  const form = new FormData();
  form.append("project_name", input.projectName);
  form.append("ignore_existing_index", String(input.ignoreExistingIndex));
  form.append("consult_existing_index", String(input.consultExistingIndex));

  Array.from(input.files).forEach((file) => {
    form.append("files", file);
  });

  const data = await requestJson<{ project: Project }>("/api/projects", {
    method: "POST",
    body: form
  });
  return data.project;
}

export async function embedProject(projectId: string): Promise<Project> {
  const data = await requestJson<{ project: Project }>(`/api/projects/${projectId}/embed`, {
    method: "POST"
  });
  return data.project;
}

export type QuestionResponse = {
  answer: string;
  answer_status: string;
  content_outcome?: "valid_complete" | "valid_partial" | "insufficient_evidence" | null;
  answer_strategy?: AnswerStrategy;
  answer_strategy_version?: string | null;
  evidence_decision?: string;
  run_diagnostics?: AnswerRunDiagnostics;
  resolved_query?: string;
  archivist_mode: ArchivistModeId;
  archivist_mode_version?: string;
  influence_profile_id?: string;
  influence_profile_version?: string;
  historiographical_lens: HistoriographicalLens;
  voice: AnswerVoice;
  worldview: AnswerWorldview;
  source_schema?: "archivist.public_sources/1";
  sources: SourceReference[];
  display_groups?: DisplayGroup[];
  costs?: CostSummary | null;
};

type QuestionOptions = {
  conversationId: string;
  turnId: string;
  archivistMode: ArchivistModeId;
  allowOverBudget?: boolean;
  publicDemo?: boolean;
  answerStrategy?: AnswerStrategy;
  signal?: AbortSignal;
};

const PUBLIC_HISTORY_TURN_LIMIT = 1;
const PUBLIC_HISTORY_QUESTION_CHARACTERS = 1_500;
const PUBLIC_HISTORY_ANSWER_CHARACTERS = 1_000;

function requestHistory(
  history: ConversationHistoryTurn[],
  publicDemo: boolean | undefined
) {
  if (!publicDemo) return history;
  return history.slice(-PUBLIC_HISTORY_TURN_LIMIT).map((turn) => ({
    ...turn,
    question: turn.question.slice(0, PUBLIC_HISTORY_QUESTION_CHARACTERS),
    answer: turn.answer.slice(0, PUBLIC_HISTORY_ANSWER_CHARACTERS)
  }));
}

function questionRequestBody(
  question: string,
  nResults: number,
  facets: AnswerFacets,
  history: ConversationHistoryTurn[],
  options: QuestionOptions
) {
  const body: Record<string, unknown> = {
    question,
    historiographical_lens: facets.historiographicalLens,
    voice: facets.voice,
    worldview: facets.worldview,
    history: requestHistory(history, options.publicDemo),
    conversation_id: options.conversationId,
    turn_id: options.turnId,
    archivist_mode: options.archivistMode,
    answer_strategy: options.answerStrategy ?? DEFAULT_ANSWER_STRATEGY
  };
  if (!options.publicDemo) {
    body.n_results = nResults;
    body.allow_over_budget = options.allowOverBudget ?? false;
  }
  return body;
}

export async function askQuestion(
  projectId: string,
  question: string,
  nResults: number,
  facets: AnswerFacets,
  history: ConversationHistoryTurn[],
  options: QuestionOptions
) {
  return requestJson<QuestionResponse>(
    `/api/projects/${projectId}/question`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(questionRequestBody(question, nResults, facets, history, options)),
      signal: options.signal
    }
  );
}

type ProgressiveFrameBase = {
  schema: "archivist.answer_stream/2";
  sequence: number;
};

type ProgressiveFrame = ProgressiveFrameBase & (
  | { type: "stage"; stage: ProgressiveAnswerStage; message: string }
  | { type: "heartbeat" }
  | {
      type: "checked_claim";
      claim_index: number;
      paragraph: number;
      text: string;
    }
  | { type: "complete"; result: QuestionResponse }
  | { type: "error"; error: { code: string; message: string; request_id?: string } }
);

const PROGRESSIVE_STAGE_ORDER: readonly ProgressiveAnswerStage[] = [
  "accepted",
  "checking_corpus",
  "resolving_question",
  "planning_search",
  "retrieving_sources",
  "checking_evidence",
  "preparing_context",
  "generating_answer",
  "validating_answer",
  "checking_release"
];
const PROGRESSIVE_STAGES = new Set<ProgressiveAnswerStage>(PROGRESSIVE_STAGE_ORDER);
const PROGRESSIVE_STAGE_INDEX = new Map(
  PROGRESSIVE_STAGE_ORDER.map((stage, index) => [stage, index] as const)
);

function progressiveFrame(value: unknown): ProgressiveFrame {
  if (!value || typeof value !== "object") {
    throw new Error("Archivist received an invalid progressive response frame.");
  }
  const frame = value as Record<string, unknown>;
  if (
    frame.schema !== "archivist.answer_stream/2"
    || !Number.isSafeInteger(frame.sequence)
    || (frame.sequence as number) < 0
  ) {
    throw new Error("Archivist received an incompatible progressive response frame.");
  }
  const base: ProgressiveFrameBase = {
    schema: "archivist.answer_stream/2",
    sequence: frame.sequence as number
  };
  if (
    frame.type === "stage"
    && typeof frame.stage === "string"
    && PROGRESSIVE_STAGES.has(frame.stage as ProgressiveAnswerStage)
    && typeof frame.message === "string"
  ) {
    return {
      ...base,
      type: "stage",
      stage: frame.stage as ProgressiveAnswerStage,
      message: frame.message
    };
  }
  if (frame.type === "heartbeat") {
    return { ...base, type: "heartbeat" };
  }
  if (
    frame.type === "checked_claim"
    && Number.isSafeInteger(frame.claim_index)
    && Number.isSafeInteger(frame.paragraph)
    && typeof frame.text === "string"
  ) {
    return {
      ...base,
      type: "checked_claim",
      claim_index: frame.claim_index as number,
      paragraph: frame.paragraph as number,
      text: frame.text
    };
  }
  if (frame.type === "complete" && isQuestionResponse(frame.result)) {
    return { ...base, type: "complete", result: frame.result as QuestionResponse };
  }
  if (frame.type === "error" && frame.error && typeof frame.error === "object") {
    const streamError = frame.error as Record<string, unknown>;
    if (typeof streamError.code !== "string" || typeof streamError.message !== "string") {
      throw new Error("Archivist received an invalid progressive error frame.");
    }
    return {
      ...base,
      type: "error",
      error: {
        code: streamError.code,
        message: streamError.message,
        request_id: typeof streamError.request_id === "string" ? streamError.request_id : undefined
      }
    };
  }
  throw new Error("Archivist received an unknown progressive response frame.");
}

export function progressiveCheckedClaimsText(claims: readonly ProgressiveCheckedClaim[]) {
  let text = "";
  let previousParagraph: number | null = null;
  for (const claim of claims) {
    if (text) text += claim.paragraph === previousParagraph ? " " : "\n\n";
    text += claim.text;
    previousParagraph = claim.paragraph;
  }
  return text;
}

function isQuestionResponse(value: unknown): value is QuestionResponse {
  if (!value || typeof value !== "object") return false;
  const result = value as Record<string, unknown>;
  return (
    typeof result.answer === "string"
    && typeof result.answer_status === "string"
    && typeof result.archivist_mode === "string"
    && typeof result.historiographical_lens === "string"
    && typeof result.voice === "string"
    && typeof result.worldview === "string"
    && Array.isArray(result.sources)
  );
}

export function isProgressiveFallbackEligible(error: unknown) {
  return error instanceof ProgressiveUnavailableError
    && (error.status === 404 || error.status === 405 || error.status === 501);
}

export async function askQuestionProgressively(
  projectId: string,
  question: string,
  nResults: number,
  facets: AnswerFacets,
  history: ConversationHistoryTurn[],
  options: QuestionOptions & {
    onStage?: (update: ProgressiveStageUpdate) => void;
    onHeartbeat?: (update: ProgressiveHeartbeatUpdate) => void;
    onCheckedClaim?: (claim: ProgressiveCheckedClaim) => void | Promise<void>;
  }
): Promise<QuestionResponse> {
  const { onStage, onHeartbeat, onCheckedClaim, ...requestOptions } = options;
  const response = await fetch(`/api/projects/${projectId}/question/progressive`, {
    method: "POST",
    headers: {
      "Accept": "application/x-ndjson",
      "Content-Type": "application/json"
    },
    body: JSON.stringify(questionRequestBody(question, nResults, facets, history, requestOptions)),
    signal: requestOptions.signal
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    const data = contentType.includes("application/json") ? await response.json() : null;
    const detail = data?.detail ?? response.statusText;
    const message = detailMessage(detail, response.statusText);
    if (response.status === 404 || response.status === 405 || response.status === 501) {
      throw new ProgressiveUnavailableError(response.status, message, detail);
    }
    throw new ApiRequestError(response.status, message, detail);
  }
  if (!response.body) {
    throw new ProgressiveStreamError("This browser could not read Archivist's progressive response.", false);
  }

  let receivedStreamEvent = false;
  let terminal: QuestionResponse | null = null;
  let terminalError: ProgressiveStreamError | null = null;
  let lastSequence = -1;
  let accepted = false;
  let heartbeatCount = 0;
  let expectedClaimIndex = 1;
  let lastClaimParagraph = 0;
  let accumulatedClaimCharacters = 0;
  const checkedClaims: ProgressiveCheckedClaim[] = [];
  const seenStages = new Set<ProgressiveAnswerStage>();
  let lastStageIndex = -1;
  try {
    await readNdjson(response.body, async (value) => {
      if (terminal || terminalError) {
        throw new Error("Archivist received data after a terminal progressive response frame.");
      }
      const frame = progressiveFrame(value);
      if (frame.sequence <= lastSequence) {
        throw new Error("Archivist received progressive response frames out of order.");
      }
      lastSequence = frame.sequence;
      receivedStreamEvent = true;
      if (!accepted) {
        if (frame.type !== "stage" || frame.stage !== "accepted") {
          throw new Error("Archivist's progressive response did not begin with acceptance.");
        }
        accepted = true;
      } else if (frame.type === "stage" && frame.stage === "accepted") {
        throw new Error("Archivist received a duplicate progressive acceptance frame.");
      }
      if (frame.type === "stage") {
        if (
          checkedClaims.length
          && frame.stage !== "validating_answer"
          && frame.stage !== "checking_release"
        ) {
          throw new Error("Archivist received a non-final progress stage after checked claims began.");
        }
        const stageIndex = PROGRESSIVE_STAGE_INDEX.get(frame.stage);
        if (
          stageIndex === undefined
          || stageIndex < lastStageIndex
          || seenStages.has(frame.stage)
        ) {
          throw new Error("Archivist received progressive stages out of order.");
        }
        lastStageIndex = stageIndex;
        seenStages.add(frame.stage);
        onStage?.({
          stage: frame.stage,
          message: PROGRESSIVE_STAGE_COPY[frame.stage]
        });
      } else if (frame.type === "heartbeat") {
        heartbeatCount += 1;
        onHeartbeat?.({ count: heartbeatCount });
        return;
      } else if (frame.type === "checked_claim") {
        if (!seenStages.has("generating_answer")) {
          throw new Error("Archivist received a checked claim before answer generation began.");
        }
        if (
          frame.claim_index !== expectedClaimIndex
          || frame.claim_index < 1
          || frame.claim_index > MAX_PROGRESSIVE_CLAIMS
        ) {
          throw new Error("Archivist received checked claims out of order.");
        }
        if (
          frame.paragraph < 1
          || frame.paragraph > MAX_PROGRESSIVE_PARAGRAPH
          || frame.paragraph < lastClaimParagraph
        ) {
          throw new Error("Archivist received an invalid checked-claim paragraph.");
        }
        if (
          !frame.text
          || frame.text !== frame.text.trim()
          || /[\r\n]/.test(frame.text)
          || frame.text.length > MAX_PROGRESSIVE_CLAIM_CHARACTERS
          || !/\[Source \d+(?:, Source \d+)*\][.!?]$/.test(frame.text)
        ) {
          throw new Error("Archivist received an invalid checked claim.");
        }
        if (
          accumulatedClaimCharacters + frame.text.length
          > MAX_PROGRESSIVE_CLAIM_CHARACTERS_TOTAL
        ) {
          throw new Error("Archivist's checked claims exceeded the client safety limit.");
        }
        const claim: ProgressiveCheckedClaim = {
          claimIndex: frame.claim_index,
          paragraph: frame.paragraph,
          text: frame.text
        };
        expectedClaimIndex += 1;
        lastClaimParagraph = frame.paragraph;
        accumulatedClaimCharacters += frame.text.length;
        checkedClaims.push(claim);
        await onCheckedClaim?.(claim);
      } else if (frame.type === "complete") {
        const requiredStage: ProgressiveAnswerStage = requestOptions.publicDemo
          ? "checking_release"
          : "validating_answer";
        if (!seenStages.has(requiredStage)) {
          throw new Error("Archivist completed an answer before the required checks finished.");
        }
        if (checkedClaims.some((claim) => !frame.result.answer.includes(claim.text))) {
          throw new Error("Archivist's checked claims did not match its canonical answer.");
        }
        terminal = frame.result;
      } else {
        const discarded = checkedClaims.length
          ? " The incomplete checked-claim assembly was discarded."
          : "";
        terminalError = new ProgressiveStreamError(
          `${frame.error.message}${discarded}`,
          true,
          frame.error.code
        );
      }
    });
  } catch (error) {
    if (error instanceof ProgressiveStreamError) throw error;
    const discarded = checkedClaims.length
      ? " The incomplete checked-claim assembly was discarded."
      : "";
    throw new ProgressiveStreamError(
      `${error instanceof Error ? error.message : "Archivist's progressive response was interrupted."}${discarded}`,
      receivedStreamEvent
    );
  }
  if (terminalError) throw terminalError;
  if (!terminal) {
    const discarded = checkedClaims.length
      ? " The incomplete checked-claim assembly was discarded."
      : "";
    throw new ProgressiveStreamError(
      `Archivist's progressive response ended before a verified answer arrived.${discarded}`,
      receivedStreamEvent
    );
  }
  return terminal;
}

function unwrapCostSummary(data: CostSummary | { costs?: CostSummary; summary?: CostSummary }) {
  if ("costs" in data && data.costs) return data.costs;
  if ("summary" in data && data.summary) return data.summary;
  return data as CostSummary;
}

function unwrapCostSettings(
  data: CostSettings
    | CostSummary
    | { settings?: CostSettings; costs?: CostSummary; summary?: CostSummary }
): CostSettings {
  let settings: CostSettings;
  if ("settings" in data && data.settings) settings = data.settings;
  else if ("costs" in data && data.costs) settings = data.costs.budget;
  else if ("summary" in data && data.summary) settings = data.summary.budget;
  else if ("budget" in data) settings = data.budget;
  else settings = data as CostSettings;
  return {
    monthly_budget_usd: settings.monthly_budget_usd,
    warning_threshold_percent: settings.warning_threshold_percent,
    hard_limit_enabled: settings.hard_limit_enabled
  };
}

export async function getCostSummary(projectId: string, conversationId: string) {
  const params = new URLSearchParams({
    project_id: projectId,
    conversation_id: conversationId
  });
  const data = await requestJson<CostSummary | { costs?: CostSummary; summary?: CostSummary }>(
    `/api/costs/summary?${params.toString()}`
  );
  return unwrapCostSummary(data);
}

export async function getCostSettings() {
  const data = await requestJson<
    CostSettings | CostSummary | { settings?: CostSettings; costs?: CostSummary; summary?: CostSummary }
  >("/api/costs/settings");
  return unwrapCostSettings(data);
}

export async function updateCostSettings(settings: CostSettings) {
  const data = await requestJson<
    CostSettings | CostSummary | { settings?: CostSettings; costs?: CostSummary; summary?: CostSummary }
  >("/api/costs/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings)
  });
  return unwrapCostSettings(data);
}

export async function generateIndexEntry(
  projectId: string,
  term: string,
  consultExistingIndex: boolean
) {
  return requestJson<{
    entry: string;
    sources: SourceChunk[];
    display_groups: DisplayGroup[];
    existing_index_sources: SourceChunk[];
  }>(`/api/projects/${projectId}/index/entry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ term, consult_existing_index: consultExistingIndex })
  });
}

export async function searchExistingIndex(projectId: string, term: string) {
  const params = new URLSearchParams({ term });
  return requestJson<{ results: SourceChunk[] }>(
    `/api/projects/${projectId}/index/search?${params.toString()}`
  );
}

export async function getCandidateTerms(projectId: string, limit = 60) {
  const data = await requestJson<{ terms: CandidateTerm[] }>(
    `/api/projects/${projectId}/index/candidates?limit=${limit}`
  );
  return data.terms;
}

export async function getManuscriptSources(
  projectId: string,
  offset = 0,
  limit = 12,
  search = "",
  document = ""
) {
  const params = new URLSearchParams({ offset: String(offset), limit: String(limit) });
  if (search) params.set("search", search);
  if (document) params.set("document", document);
  return requestJson<{ total: number; sources: SourceChunk[]; documents: string[] }>(
    `/api/projects/${projectId}/sources?${params.toString()}`
  );
}
