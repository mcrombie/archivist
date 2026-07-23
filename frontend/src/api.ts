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

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const contentType = response.headers.get("content-type") ?? "";
  const data = contentType.includes("application/json") ? await response.json() : null;

  if (!response.ok) {
    const detail = data?.detail ?? response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
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
  perspective: AnswerPerspective = "neutral",
  history: ConversationHistoryTurn[] = []
) {
  return requestJson<{
    answer: string;
    resolved_query: string;
    perspective: AnswerPerspective;
    sources: SourceChunk[];
    display_groups: DisplayGroup[];
  }>(
    `/api/projects/${projectId}/question`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, n_results: nResults, perspective, history })
    }
  );
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
