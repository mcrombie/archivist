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

export type SourceChunk = {
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

export type DisplayGroup = {
  source_numbers: number[];
  text: string;
  citation_labels: string[];
};

export type ConversationHistoryTurn = {
  question: string;
  answer: string;
};

export type AnswerRunDiagnostics = {
  schema: "archivist.answer_run_diagnostics/1";
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
  };
  answer_status: string;
  evidence_decision: string;
  validation_result: "valid" | "invalid" | "not_run";
  validation_error_code: string | null;
  repair_applied: boolean;
  repair_codes: string[];
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

export async function askQuestion(
  projectId: string,
  question: string,
  nResults: number,
  facets: AnswerFacets,
  history: ConversationHistoryTurn[],
  options: {
    conversationId: string;
    turnId: string;
    allowOverBudget?: boolean;
  }
) {
  return requestJson<{
    answer: string;
    answer_status: string;
    evidence_decision: string;
    run_diagnostics: AnswerRunDiagnostics;
    resolved_query: string;
    historiographical_lens: HistoriographicalLens;
    voice: AnswerVoice;
    worldview: AnswerWorldview;
    sources: SourceChunk[];
    display_groups: DisplayGroup[];
    costs: CostSummary | null;
  }>(
    `/api/projects/${projectId}/question`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        n_results: nResults,
        historiographical_lens: facets.historiographicalLens,
        voice: facets.voice,
        worldview: facets.worldview,
        history,
        conversation_id: options.conversationId,
        turn_id: options.turnId,
        allow_over_budget: options.allowOverBudget ?? false
      })
    }
  );
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
