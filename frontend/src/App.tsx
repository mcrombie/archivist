import {
  AlertCircle,
  Archive,
  BookOpen,
  CheckCircle2,
  Database,
  FileSearch,
  FileText,
  ListTree,
  Loader2,
  Search,
  Send,
  Settings,
  Upload
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  CandidateTerm,
  Project,
  SourceChunk,
  askQuestion,
  createProject,
  embedProject,
  generateIndexEntry,
  getCandidateTerms,
  listProjects,
  searchExistingIndex
} from "./api";

type Mode = "question" | "index" | "existing";
type Notice = { type: "info" | "error" | "success"; text: string } | null;

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string>("current");
  const [mode, setMode] = useState<Mode>("question");
  const [notice, setNotice] = useState<Notice>(null);
  const [loadingProjects, setLoadingProjects] = useState(true);

  const activeProject = useMemo(
    () => projects.find((project) => project.id === activeProjectId) ?? projects[0],
    [activeProjectId, projects]
  );

  async function refreshProjects(nextProjectId?: string) {
    setLoadingProjects(true);
    try {
      const nextProjects = await listProjects();
      setProjects(nextProjects);
      if (nextProjectId) {
        setActiveProjectId(nextProjectId);
      } else if (!nextProjects.some((project) => project.id === activeProjectId)) {
        setActiveProjectId(nextProjects[0]?.id ?? "current");
      }
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoadingProjects(false);
    }
  }

  useEffect(() => {
    refreshProjects();
  }, []);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <Archive size={24} />
          <div>
            <h1>Archivist</h1>
            <p>Manuscript workbench</p>
          </div>
        </div>

        <section className="side-section">
          <div className="side-heading">
            <BookOpen size={16} />
            <span>Projects</span>
          </div>
          <div className="project-list">
            {loadingProjects ? (
              <div className="muted-row">
                <Loader2 size={16} className="spin" />
                Loading
              </div>
            ) : (
              projects.map((project) => (
                <button
                  key={project.id}
                  className={`project-button ${project.id === activeProject?.id ? "active" : ""}`}
                  onClick={() => setActiveProjectId(project.id)}
                >
                  <span>{project.name}</span>
                  {project.embedded ? <CheckCircle2 size={15} /> : <AlertCircle size={15} />}
                </button>
              ))
            )}
          </div>
        </section>

        {activeProject ? <ProjectStatus project={activeProject} onRefresh={refreshProjects} setNotice={setNotice} /> : null}
      </aside>

      <section className="workspace">
        {notice ? <NoticeBar notice={notice} onDismiss={() => setNotice(null)} /> : null}

        <UploadPanel onCreated={(project) => refreshProjects(project.id)} setNotice={setNotice} />

        {activeProject ? (
          <>
            <header className="workspace-header">
              <div>
                <p className="eyebrow">Active project</p>
                <h2>{activeProject.name}</h2>
              </div>
              <div className="mode-tabs" role="tablist" aria-label="Archivist mode">
                <button className={mode === "question" ? "active" : ""} onClick={() => setMode("question")}>
                  <FileSearch size={16} />
                  Question
                </button>
                <button className={mode === "index" ? "active" : ""} onClick={() => setMode("index")}>
                  <ListTree size={16} />
                  Index
                </button>
                <button className={mode === "existing" ? "active" : ""} onClick={() => setMode("existing")}>
                  <Search size={16} />
                  Existing
                </button>
              </div>
            </header>

            {mode === "question" ? <QuestionMode project={activeProject} setNotice={setNotice} /> : null}
            {mode === "index" ? <IndexMode project={activeProject} setNotice={setNotice} /> : null}
            {mode === "existing" ? <ExistingIndexMode project={activeProject} setNotice={setNotice} /> : null}
          </>
        ) : null}
      </section>
    </main>
  );
}

function ProjectStatus({
  project,
  onRefresh,
  setNotice
}: {
  project: Project;
  onRefresh: (projectId?: string) => Promise<void>;
  setNotice: (notice: Notice) => void;
}) {
  const [embedding, setEmbedding] = useState(false);

  async function handleEmbed() {
    setEmbedding(true);
    setNotice({ type: "info", text: "Building search index" });
    try {
      const updated = await embedProject(project.id);
      await onRefresh(updated.id);
      setNotice({ type: "success", text: "Search index ready" });
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setEmbedding(false);
    }
  }

  return (
    <section className="side-section status-panel">
      <div className="side-heading">
        <Database size={16} />
        <span>Status</span>
      </div>
      <dl className="stat-grid">
        <div>
          <dt>Files</dt>
          <dd>{project.stats.source_files}</dd>
        </div>
        <div>
          <dt>Chunks</dt>
          <dd>{project.stats.searchable_chunks}</dd>
        </div>
        <div>
          <dt>Index refs</dt>
          <dd>{project.stats.existing_index_chunks}</dd>
        </div>
        <div>
          <dt>Embedded</dt>
          <dd>{project.embedded_chunks}</dd>
        </div>
      </dl>

      <div className="settings-list">
        <span>
          <Settings size={14} />
          {project.settings.ignore_existing_index ? "Ignoring existing index" : "Index included"}
        </span>
        <span>
          <Settings size={14} />
          {project.settings.consult_existing_index ? "Consulting existing index" : "No index consultation"}
        </span>
      </div>

      <button className="primary-button full" onClick={handleEmbed} disabled={embedding || project.is_builtin}>
        {embedding ? <Loader2 size={16} className="spin" /> : <Database size={16} />}
        {project.embedded ? "Rebuild Index" : "Build Search Index"}
      </button>
    </section>
  );
}

function UploadPanel({
  onCreated,
  setNotice
}: {
  onCreated: (project: Project) => void;
  setNotice: (notice: Notice) => void;
}) {
  const [projectName, setProjectName] = useState("First edition manuscript");
  const [files, setFiles] = useState<FileList | null>(null);
  const [ignoreExistingIndex, setIgnoreExistingIndex] = useState(true);
  const [consultExistingIndex, setConsultExistingIndex] = useState(true);
  const [creating, setCreating] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!files?.length) {
      setNotice({ type: "error", text: "Select at least one .md, .txt, or .zip file" });
      return;
    }

    setCreating(true);
    try {
      const project = await createProject({
        projectName,
        ignoreExistingIndex,
        consultExistingIndex,
        files
      });
      onCreated(project);
      setNotice({ type: "success", text: "Project processed" });
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setCreating(false);
    }
  }

  return (
    <form className="upload-band" onSubmit={handleSubmit}>
      <div className="upload-fields">
        <label>
          <span>Project name</span>
          <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
        </label>
        <label className="file-input">
          <span>Manuscript files</span>
          <input
            type="file"
            multiple
            accept=".md,.txt,.zip"
            onChange={(event) => setFiles(event.target.files)}
          />
        </label>
      </div>
      <div className="upload-options">
        <label className="check-row">
          <input
            type="checkbox"
            checked={ignoreExistingIndex}
            onChange={(event) => setIgnoreExistingIndex(event.target.checked)}
          />
          Ignore existing index
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={consultExistingIndex}
            onChange={(event) => setConsultExistingIndex(event.target.checked)}
          />
          Consult existing index
        </label>
      </div>
      <button className="primary-button" type="submit" disabled={creating}>
        {creating ? <Loader2 size={16} className="spin" /> : <Upload size={16} />}
        Process
      </button>
    </form>
  );
}

function QuestionMode({ project, setNotice }: { project: Project; setNotice: (notice: Notice) => void }) {
  const [question, setQuestion] = useState("What role did Jamestown play as a corporate experiment?");
  const [nResults, setNResults] = useState(5);
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<SourceChunk[]>([]);
  const [loading, setLoading] = useState(false);

  async function submitQuestion(event: FormEvent) {
    event.preventDefault();
    if (!project.embedded) {
      setNotice({ type: "error", text: "Build the search index first" });
      return;
    }
    setLoading(true);
    try {
      const result = await askQuestion(project.id, question, nResults);
      setAnswer(result.answer);
      setSources(result.sources);
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mode-grid">
      <form className="tool-panel" onSubmit={submitQuestion}>
        <label>
          <span>Question</span>
          <textarea value={question} onChange={(event) => setQuestion(event.target.value)} rows={6} />
        </label>
        <div className="inline-controls">
          <label>
            <span>Retrieval count</span>
            <input
              type="number"
              min={1}
              max={12}
              value={nResults}
              onChange={(event) => setNResults(Number(event.target.value))}
            />
          </label>
          <button className="primary-button" disabled={loading}>
            {loading ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
            Ask
          </button>
        </div>
      </form>

      <ResultPanel title="Answer" body={answer} empty="No answer yet" />
      <SourceList sources={sources} title="Sources" />
    </section>
  );
}

function IndexMode({ project, setNotice }: { project: Project; setNotice: (notice: Notice) => void }) {
  const [term, setTerm] = useState("Virginia Company");
  const [consultExistingIndex, setConsultExistingIndex] = useState(project.settings.consult_existing_index);
  const [entry, setEntry] = useState("");
  const [sources, setSources] = useState<SourceChunk[]>([]);
  const [existingSources, setExistingSources] = useState<SourceChunk[]>([]);
  const [terms, setTerms] = useState<CandidateTerm[]>([]);
  const [loadingTerms, setLoadingTerms] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    setConsultExistingIndex(project.settings.consult_existing_index);
    setTerms([]);
    setEntry("");
    setSources([]);
    setExistingSources([]);
  }, [project.id]);

  async function loadTerms() {
    setLoadingTerms(true);
    try {
      setTerms(await getCandidateTerms(project.id));
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoadingTerms(false);
    }
  }

  async function submitTerm(event: FormEvent) {
    event.preventDefault();
    if (!project.embedded) {
      setNotice({ type: "error", text: "Build the search index first" });
      return;
    }
    setGenerating(true);
    try {
      const result = await generateIndexEntry(project.id, term, consultExistingIndex);
      setEntry(result.entry);
      setSources(result.sources);
      setExistingSources(result.existing_index_sources);
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setGenerating(false);
    }
  }

  return (
    <section className="index-layout">
      <div className="tool-panel">
        <div className="panel-header">
          <h3>Candidate terms</h3>
          <button className="icon-button" type="button" onClick={loadTerms} title="Refresh terms">
            {loadingTerms ? <Loader2 size={16} className="spin" /> : <Search size={16} />}
          </button>
        </div>
        <div className="term-list">
          {terms.length ? (
            terms.map((candidate) => (
              <button key={candidate.term} onClick={() => setTerm(candidate.term)}>
                <span>{candidate.term}</span>
                <small>{candidate.count}</small>
              </button>
            ))
          ) : (
            <p className="empty-state">No terms loaded</p>
          )}
        </div>
      </div>

      <div className="mode-grid compact">
        <form className="tool-panel" onSubmit={submitTerm}>
          <label>
            <span>Index term</span>
            <input value={term} onChange={(event) => setTerm(event.target.value)} />
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={consultExistingIndex}
              disabled={!project.stats.existing_index_chunks}
              onChange={(event) => setConsultExistingIndex(event.target.checked)}
            />
            Consult existing index
          </label>
          <button className="primary-button" disabled={generating}>
            {generating ? <Loader2 size={16} className="spin" /> : <ListTree size={16} />}
            Generate Entry
          </button>
        </form>

        <ResultPanel title="Candidate entry" body={entry} empty="No entry yet" />
        <SourceList sources={sources} title="Manuscript sources" />
        <SourceList sources={existingSources} title="Existing index references" />
      </div>
    </section>
  );
}

function ExistingIndexMode({ project, setNotice }: { project: Project; setNotice: (notice: Notice) => void }) {
  const [term, setTerm] = useState("Virginia Company");
  const [results, setResults] = useState<SourceChunk[]>([]);
  const [loading, setLoading] = useState(false);

  async function submitSearch(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    try {
      const data = await searchExistingIndex(project.id, term);
      setResults(data.results);
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="mode-grid">
      <form className="tool-panel" onSubmit={submitSearch}>
        <label>
          <span>Existing index term</span>
          <input value={term} onChange={(event) => setTerm(event.target.value)} />
        </label>
        <button className="primary-button" disabled={loading || !project.stats.existing_index_chunks}>
          {loading ? <Loader2 size={16} className="spin" /> : <Search size={16} />}
          Search
        </button>
      </form>
      <SourceList sources={results} title="Matches" />
    </section>
  );
}

function ResultPanel({ title, body, empty }: { title: string; body: string; empty: string }) {
  return (
    <section className="result-panel">
      <div className="panel-header">
        <h3>{title}</h3>
        <FileText size={16} />
      </div>
      {body ? <pre>{body}</pre> : <p className="empty-state">{empty}</p>}
    </section>
  );
}

function SourceList({ title, sources }: { title: string; sources: SourceChunk[] }) {
  return (
    <section className="sources-panel">
      <div className="panel-header">
        <h3>{title}</h3>
        <span>{sources.length}</span>
      </div>
      <div className="source-list">
        {sources.length ? (
          sources.map((source) => (
            <details key={`${source.chunk_id}-${source.source_number}`} className="source-card">
              <summary>
                <span>
                  Source {source.source_number}: {source.chapter_title}
                </span>
                <small>
                  {source.chunk_id} | {source.paragraph_start}-{source.paragraph_end}
                </small>
              </summary>
              <p>{source.text}</p>
            </details>
          ))
        ) : (
          <p className="empty-state">No sources</p>
        )}
      </div>
    </section>
  );
}

function NoticeBar({ notice, onDismiss }: { notice: Exclude<Notice, null>; onDismiss: () => void }) {
  return (
    <button className={`notice ${notice.type}`} onClick={onDismiss}>
      {notice.type === "error" ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
      <span>{notice.text}</span>
    </button>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong";
}

export default App;
