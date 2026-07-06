import {
  Archive,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  FileSearch,
  FileText,
  Library,
  ListTree,
  Loader2,
  Search,
  Send,
  Upload
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
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

type AppStage = "welcome" | "choose" | "question" | "index";
type Notice = { type: "error" | "success" | "info"; text: string } | null;

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [stage, setStage] = useState<AppStage>("welcome");
  const [notice, setNotice] = useState<Notice>(null);

  const currentProject = useMemo(
    () => projects.find((project) => project.id === "current") ?? null,
    [projects]
  );

  async function refreshProjects(nextProjectId?: string) {
    const nextProjects = await listProjects();
    setProjects(nextProjects);
    if (nextProjectId) {
      const nextProject = nextProjects.find((project) => project.id === nextProjectId);
      if (nextProject) {
        setActiveProject(nextProject);
      }
    }
  }

  useEffect(() => {
    refreshProjects().catch((error) => {
      setNotice({ type: "error", text: errorMessage(error) });
    });
  }, []);

  function selectProject(project: Project) {
    setActiveProject(project);
    setStage("choose");
    setNotice(null);
  }

  return (
    <main className="library-shell">
      <div className="library-grain" />
      <header className="app-header">
        <div className="brand-mark">
          <Library size={25} />
          <span>Archivist</span>
        </div>
        {activeProject ? (
          <button className="ghost-button" onClick={() => setStage("welcome")}>
            <ArrowLeft size={16} />
            New Manuscript
          </button>
        ) : null}
      </header>

      {notice ? <NoticeBanner notice={notice} onClose={() => setNotice(null)} /> : null}

      {stage === "welcome" ? (
        <WelcomeScreen
          currentProject={currentProject}
          onProjectReady={(project) => {
            setActiveProject(project);
            setStage("choose");
          }}
          onUseCurrent={selectProject}
          refreshProjects={refreshProjects}
          setNotice={setNotice}
        />
      ) : null}

      {stage === "choose" && activeProject ? (
        <ModeChooser
          project={activeProject}
          onQuestion={() => setStage("question")}
          onIndex={() => setStage("index")}
        />
      ) : null}

      {stage === "question" && activeProject ? (
        <QuestionMode project={activeProject} onBack={() => setStage("choose")} setNotice={setNotice} />
      ) : null}

      {stage === "index" && activeProject ? (
        <IndexMode project={activeProject} onBack={() => setStage("choose")} setNotice={setNotice} />
      ) : null}
    </main>
  );
}

function WelcomeScreen({
  currentProject,
  onProjectReady,
  onUseCurrent,
  refreshProjects,
  setNotice
}: {
  currentProject: Project | null;
  onProjectReady: (project: Project) => void;
  onUseCurrent: (project: Project) => void;
  refreshProjects: (projectId?: string) => Promise<void>;
  setNotice: (notice: Notice) => void;
}) {
  const [projectName, setProjectName] = useState("Untitled manuscript");
  const [files, setFiles] = useState<FileList | null>(null);
  const [ignoreExistingIndex, setIgnoreExistingIndex] = useState(true);
  const [consultExistingIndex, setConsultExistingIndex] = useState(true);
  const [processing, setProcessing] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!files?.length) {
      setNotice({ type: "error", text: "Select a manuscript file first." });
      return;
    }

    setProcessing(true);
    setNotice({ type: "info", text: "Preparing the manuscript." });
    try {
      const created = await createProject({
        projectName,
        ignoreExistingIndex,
        consultExistingIndex,
        files
      });

      let readyProject = created;
      try {
        setNotice({ type: "info", text: "Building the search index." });
        readyProject = await embedProject(created.id);
      } catch (error) {
        setNotice({ type: "error", text: `Project created, but indexing failed: ${errorMessage(error)}` });
      }

      await refreshProjects(readyProject.id);
      onProjectReady(readyProject);
      if (readyProject.embedded) {
        setNotice({ type: "success", text: "Manuscript processed." });
      }
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setProcessing(false);
    }
  }

  return (
    <section className="welcome-stage">
      <div className="manuscript-desk">
        <div className="desk-intro">
          <div className="seal">
            <Archive size={30} />
          </div>
          <p className="kicker">A manuscript assistant for writers</p>
          <h1>Bring a draft into the archive.</h1>
          <p>
            Archivist helps writers question, inspect, and index long manuscripts while keeping source passages close at hand.
          </p>
        </div>

        <form className="upload-form" onSubmit={submit}>
          <label>
            <span>Manuscript name</span>
            <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
          </label>

          <label className="drop-field">
            <FileText size={22} />
            <span>{files?.length ? `${files.length} file(s) selected` : "Upload manuscript"}</span>
            <input
              type="file"
              multiple
              accept=".md,.txt,.zip"
              onChange={(event) => setFiles(event.target.files)}
            />
          </label>

          <div className="option-pair">
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

          <button className="primary-button full" disabled={processing}>
            {processing ? <Loader2 size={17} className="spin" /> : <Upload size={17} />}
            Process Manuscript
          </button>
        </form>

        {currentProject ? (
          <button className="text-button" onClick={() => onUseCurrent(currentProject)}>
            Open current manuscript
          </button>
        ) : null}
      </div>
    </section>
  );
}

function ModeChooser({
  project,
  onQuestion,
  onIndex
}: {
  project: Project;
  onQuestion: () => void;
  onIndex: () => void;
}) {
  return (
    <section className="mode-stage">
      <div className="project-vellum">
        <p className="kicker">Manuscript processed</p>
        <h1>{project.name}</h1>
        <dl className="simple-stats">
          <div>
            <dt>Searchable chunks</dt>
            <dd>{project.stats.searchable_chunks}</dd>
          </div>
          <div>
            <dt>Existing index chunks</dt>
            <dd>{project.stats.existing_index_chunks}</dd>
          </div>
          <div>
            <dt>Search index</dt>
            <dd>{project.embedded ? "Ready" : "Not built"}</dd>
          </div>
        </dl>
      </div>

      <div className="mode-choice-grid">
        <button className="mode-choice" onClick={onQuestion} disabled={!project.embedded}>
          <FileSearch size={26} />
          <span>Q&A Mode</span>
          <small>Ask questions and inspect cited manuscript passages.</small>
        </button>
        <button className="mode-choice" onClick={onIndex} disabled={!project.embedded}>
          <ListTree size={26} />
          <span>Index Mode</span>
          <small>Draft index entries and compare against an existing index.</small>
        </button>
      </div>
    </section>
  );
}

function QuestionMode({
  project,
  onBack,
  setNotice
}: {
  project: Project;
  onBack: () => void;
  setNotice: (notice: Notice) => void;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<SourceChunk[]>([]);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) {
      setNotice({ type: "error", text: "Enter a question." });
      return;
    }

    setLoading(true);
    try {
      const result = await askQuestion(project.id, question, 5);
      setAnswer(result.answer);
      setSources(result.sources);
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="focused-stage">
      <ModeHeader title="Q&A Mode" project={project} onBack={onBack} icon={<FileSearch size={22} />} />
      <form className="query-panel" onSubmit={submit}>
        <label>
          <span>Question</span>
          <textarea
            rows={5}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask something about the manuscript..."
          />
        </label>
        <button className="primary-button" disabled={loading}>
          {loading ? <Loader2 size={17} className="spin" /> : <Send size={17} />}
          Ask
        </button>
      </form>

      <OutputBlock title="Answer" body={answer} empty="No answer yet." />
      <Sources title="Sources" sources={sources} />
    </section>
  );
}

function IndexMode({
  project,
  onBack,
  setNotice
}: {
  project: Project;
  onBack: () => void;
  setNotice: (notice: Notice) => void;
}) {
  const [term, setTerm] = useState("");
  const [consultExistingIndex, setConsultExistingIndex] = useState(project.settings.consult_existing_index);
  const [candidateTerms, setCandidateTerms] = useState<CandidateTerm[]>([]);
  const [entry, setEntry] = useState("");
  const [sources, setSources] = useState<SourceChunk[]>([]);
  const [existingSources, setExistingSources] = useState<SourceChunk[]>([]);
  const [indexSearch, setIndexSearch] = useState("");
  const [indexMatches, setIndexMatches] = useState<SourceChunk[]>([]);
  const [loadingTerms, setLoadingTerms] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [searching, setSearching] = useState(false);

  async function loadTerms() {
    setLoadingTerms(true);
    try {
      setCandidateTerms(await getCandidateTerms(project.id, 40));
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setLoadingTerms(false);
    }
  }

  async function submitEntry(event: FormEvent) {
    event.preventDefault();
    if (!term.trim()) {
      setNotice({ type: "error", text: "Enter an index term." });
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

  async function submitIndexSearch(event: FormEvent) {
    event.preventDefault();
    if (!indexSearch.trim()) {
      return;
    }
    setSearching(true);
    try {
      const result = await searchExistingIndex(project.id, indexSearch);
      setIndexMatches(result.results);
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setSearching(false);
    }
  }

  return (
    <section className="focused-stage">
      <ModeHeader title="Index Mode" project={project} onBack={onBack} icon={<ListTree size={22} />} />

      <div className="index-workspace">
        <section className="term-panel">
          <div className="panel-title">
            <h2>Terms</h2>
            <button className="small-button" onClick={loadTerms}>
              {loadingTerms ? <Loader2 size={15} className="spin" /> : <Search size={15} />}
              Find
            </button>
          </div>
          <div className="term-list">
            {candidateTerms.length ? (
              candidateTerms.map((candidate) => (
                <button key={candidate.term} onClick={() => setTerm(candidate.term)}>
                  <span>{candidate.term}</span>
                  <small>{candidate.count}</small>
                </button>
              ))
            ) : (
              <p className="empty-state">No terms loaded.</p>
            )}
          </div>
        </section>

        <section className="index-main">
          <form className="query-panel" onSubmit={submitEntry}>
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
              {generating ? <Loader2 size={17} className="spin" /> : <ListTree size={17} />}
              Generate Entry
            </button>
          </form>

          <OutputBlock title="Candidate entry" body={entry} empty="No entry yet." />

          <form className="index-search" onSubmit={submitIndexSearch}>
            <label>
              <span>Search existing index</span>
              <input value={indexSearch} onChange={(event) => setIndexSearch(event.target.value)} />
            </label>
            <button className="small-button" disabled={searching || !project.stats.existing_index_chunks}>
              {searching ? <Loader2 size={15} className="spin" /> : <Search size={15} />}
              Search
            </button>
          </form>

          <Sources title="Manuscript sources" sources={sources} />
          <Sources title="Existing index references" sources={[...existingSources, ...indexMatches]} />
        </section>
      </div>
    </section>
  );
}

function ModeHeader({
  title,
  project,
  icon,
  onBack
}: {
  title: string;
  project: Project;
  icon: ReactNode;
  onBack: () => void;
}) {
  return (
    <header className="mode-header">
      <button className="ghost-button" onClick={onBack}>
        <ArrowLeft size={16} />
        Modes
      </button>
      <div>
        <p className="kicker">{project.name}</p>
        <h1>
          {icon}
          {title}
        </h1>
      </div>
    </header>
  );
}

function OutputBlock({ title, body, empty }: { title: string; body: string; empty: string }) {
  return (
    <section className="output-block">
      <div className="panel-title">
        <h2>{title}</h2>
        <BookOpen size={17} />
      </div>
      {body ? <pre>{body}</pre> : <p className="empty-state">{empty}</p>}
    </section>
  );
}

function Sources({ title, sources }: { title: string; sources: SourceChunk[] }) {
  return (
    <section className="sources-block">
      <div className="panel-title">
        <h2>{title}</h2>
        <span>{sources.length}</span>
      </div>
      {sources.length ? (
        <div className="source-stack">
          {sources.map((source) => (
            <details key={`${source.chunk_id}-${source.source_number}`} className="source-card">
              <summary>
                <strong>Source {source.source_number}</strong>
                <span>{source.chapter_title}</span>
                <small>
                  {source.chunk_id} | {source.paragraph_start}-{source.paragraph_end}
                </small>
              </summary>
              <p>{source.text}</p>
            </details>
          ))}
        </div>
      ) : (
        <p className="empty-state">No sources.</p>
      )}
    </section>
  );
}

function NoticeBanner({ notice, onClose }: { notice: Exclude<Notice, null>; onClose: () => void }) {
  return (
    <button className={`notice-banner ${notice.type}`} onClick={onClose}>
      <CheckCircle2 size={16} />
      <span>{notice.text}</span>
    </button>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

export default App;
