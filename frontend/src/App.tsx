import {
  Archive,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  Copy,
  FileSearch,
  FileText,
  Library,
  ListTree,
  Loader2,
  Search,
  Send,
  Upload
} from "lucide-react";
import { CSSProperties, FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import {
  CandidateTerm,
  DisplayGroup,
  Project,
  SourceChunk,
  askQuestion,
  createProject,
  embedProject,
  generateIndexEntry,
  getCandidateTerms,
  getManuscriptSources,
  listProjects,
  searchExistingIndex
} from "./api";

type AppStage = "welcome" | "choose" | "viewer" | "question" | "index";
type Notice = { type: "error" | "success" | "info"; text: string } | null;

function ProcessStatus({ messages }: { messages: string[] }) {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    setMessageIndex(0);
    if (messages.length < 2) return;

    const interval = window.setInterval(() => {
      setMessageIndex((current) => Math.min(current + 1, messages.length - 1));
    }, 2400);

    return () => window.clearInterval(interval);
  }, [messages]);

  return (
    <div className="process-status" role="status" aria-live="polite">
      <span className="process-pulse" aria-hidden="true" />
      <span>{messages[messageIndex]}</span>
    </div>
  );
}

const MANUSCRIPT_IMPORT_STEPS = [
  "Uploading manuscript files...",
  "Reading document structure...",
  "Separating manuscript text from existing index material...",
  "Preparing searchable passages..."
];

const EMBEDDING_STEPS = [
  "Building the semantic search index...",
  "Embedding manuscript passages...",
  "Organizing passages for retrieval...",
  "Finalizing the searchable archive..."
];

const QUESTION_STEPS = [
  "Searching the manuscript for relevant passages...",
  "Comparing the strongest source matches...",
  "Assembling grounded context...",
  "Writing an answer with source citations..."
];

const INDEX_ENTRY_STEPS = [
  "Finding passages related to this term...",
  "Comparing uses across the manuscript...",
  "Checking relevant existing index entries...",
  "Drafting the index entry and subentries..."
];

const CANDIDATE_TERM_STEPS = [
  "Scanning the manuscript for indexable terms...",
  "Counting recurring names and concepts...",
  "Ranking candidate terms..."
];

const INDEX_SEARCH_STEPS = [
  "Searching existing index entries...",
  "Comparing nearby references...",
  "Collecting the closest matches..."
];

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
          onViewer={() => setStage("viewer")}
          onQuestion={() => setStage("question")}
          onIndex={() => setStage("index")}
          onProjectUpdated={async (project) => {
            setActiveProject(project);
            await refreshProjects(project.id);
          }}
          setNotice={setNotice}
        />
      ) : null}

      {stage === "viewer" && activeProject ? (
        <ManuscriptViewer project={activeProject} onBack={() => setStage("choose")} setNotice={setNotice} />
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
  const [processSteps, setProcessSteps] = useState(MANUSCRIPT_IMPORT_STEPS);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!files?.length) {
      setNotice({ type: "error", text: "Select a manuscript file first." });
      return;
    }

    setProcessing(true);
    setProcessSteps(MANUSCRIPT_IMPORT_STEPS);
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
        setProcessSteps(EMBEDDING_STEPS);
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
              accept=".md,.txt,.docx,.pdf,.zip"
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
          {processing ? <ProcessStatus messages={processSteps} /> : null}
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
  onViewer,
  onQuestion,
  onIndex,
  onProjectUpdated,
  setNotice
}: {
  project: Project;
  onViewer: () => void;
  onQuestion: () => void;
  onIndex: () => void;
  onProjectUpdated: (project: Project) => Promise<void>;
  setNotice: (notice: Notice) => void;
}) {
  const [buildingIndex, setBuildingIndex] = useState(false);
  const indexReady = project.embedded;

  async function buildSearchIndex() {
    setBuildingIndex(true);
    setNotice({ type: "info", text: "Building the search index." });
    try {
      const readyProject = await embedProject(project.id);
      await onProjectUpdated(readyProject);
      setNotice({ type: "success", text: "Search index built." });
    } catch (error) {
      setNotice({ type: "error", text: errorMessage(error) });
    } finally {
      setBuildingIndex(false);
    }
  }

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
            <dd>{indexReady ? "Ready" : buildingIndex ? "Building..." : "Not built"}</dd>
          </div>
        </dl>
        {!indexReady ? (
          <div className="index-status-panel">
            <p>The manuscript was imported, but Q&A and Index Mode need a search index.</p>
            <button className="primary-button" onClick={buildSearchIndex} disabled={buildingIndex}>
              {buildingIndex ? <Loader2 size={17} className="spin" /> : <Upload size={17} />}
              Build Search Index
            </button>
            {buildingIndex ? <ProcessStatus messages={EMBEDDING_STEPS} /> : null}
          </div>
        ) : null}
      </div>

      <div className="mode-choice-grid">
        <button className="mode-choice" onClick={onViewer}>
          <BookOpen size={26} />
          <span>Manuscript Viewer</span>
          <small>Read the processed manuscript and inspect its paragraph locations.</small>
        </button>
        <button className="mode-choice" onClick={onQuestion} disabled={!indexReady}>
          <FileSearch size={26} />
          <span>Q&A Mode</span>
          <small>Ask questions and inspect cited manuscript passages.</small>
        </button>
        <button className="mode-choice" onClick={onIndex} disabled={!indexReady}>
          <ListTree size={26} />
          <span>Index Mode</span>
          <small>Draft index entries and compare against an existing index.</small>
        </button>
      </div>
    </section>
  );
}

const VIEWER_PAGE_SIZE = 12;

function ManuscriptViewer({
  project,
  onBack,
  setNotice
}: {
  project: Project;
  onBack: () => void;
  setNotice: (notice: Notice) => void;
}) {
  const pdfFiles = project.source_files.filter((file) => file.toLowerCase().endsWith(".pdf"));
  const [selectedSourceFile, setSelectedSourceFile] = useState(pdfFiles[0] ?? "");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [passages, setPassages] = useState<SourceChunk[]>([]);
  const [documents, setDocuments] = useState<string[]>([]);
  const [selectedDocument, setSelectedDocument] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [fontSize, setFontSize] = useState(16);
  const [pageInput, setPageInput] = useState("1");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (selectedSourceFile) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getManuscriptSources(project.id, offset, VIEWER_PAGE_SIZE, search, selectedDocument)
      .then((result) => {
        if (!cancelled) {
          setTotal(result.total);
          setPassages(result.sources);
          setDocuments(result.documents);
        }
      })
      .catch((error) => {
        if (!cancelled) setNotice({ type: "error", text: errorMessage(error) });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [offset, project.id, search, selectedDocument, selectedSourceFile, setNotice]);

  const firstPassage = total ? offset + 1 : 0;
  const lastPassage = Math.min(offset + passages.length, total);
  const pageCount = Math.max(1, Math.ceil(total / VIEWER_PAGE_SIZE));
  const currentPage = Math.floor(offset / VIEWER_PAGE_SIZE) + 1;

  useEffect(() => setPageInput(String(currentPage)), [currentPage]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setSearch(searchInput.trim());
  }

  function jumpToPage(event: FormEvent) {
    event.preventDefault();
    const requestedPage = Number.parseInt(pageInput, 10);
    if (!Number.isFinite(requestedPage)) return;
    setOffset((Math.min(pageCount, Math.max(1, requestedPage)) - 1) * VIEWER_PAGE_SIZE);
  }


  if (selectedSourceFile) {
    const encodedPath = selectedSourceFile.split(/[\\/]/).map(encodeURIComponent).join("/");
    return (
      <section className="focused-stage viewer-focused-stage">
        <ModeHeader title="Manuscript Viewer" project={project} onBack={onBack} icon={<BookOpen size={22} />} />
        <section className="pdf-viewer-panel">
          <header className="pdf-viewer-toolbar">
            <div>
              <p className="kicker">Original manuscript</p>
              <h2>{project.name}</h2>
            </div>
            {pdfFiles.length > 1 ? (
              <label>
                <span>Document</span>
                <select value={selectedSourceFile} onChange={(event) => setSelectedSourceFile(event.target.value)}>
                  {pdfFiles.map((file) => <option key={file}>{file}</option>)}
                </select>
              </label>
            ) : <span>{selectedSourceFile}</span>}
          </header>
          <iframe title={`${project.name} manuscript`} src={`/api/projects/${project.id}/source-file/${encodedPath}`} />
        </section>
      </section>
    );
  }

  return (
    <section className="focused-stage">
      <ModeHeader title="Manuscript Viewer" project={project} onBack={onBack} icon={<BookOpen size={22} />} />
      <section className="viewer-panel">
        <header className="viewer-toolbar">
          <div>
            <p className="kicker">Processed manuscript</p>
            <h2>{project.name}</h2>
          </div>
          <span>{loading ? "Loading..." : `${firstPassage}-${lastPassage} of ${total} passages`}</span>
        </header>

        <div className="viewer-controls">
          <form className="viewer-search" onSubmit={submitSearch}>
            <label>
              <span>Search manuscript</span>
              <input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Find a name, phrase, or subject..." />
            </label>
            <button className="small-button" disabled={loading}><Search size={15} />Search</button>
            {search ? (
              <button className="viewer-clear-button" type="button" onClick={() => { setSearchInput(""); setSearch(""); setOffset(0); }}>
                Clear
              </button>
            ) : null}
          </form>

          <div className="viewer-options">
            {documents.length > 1 ? (
              <label>
                <span>Document</span>
                <select value={selectedDocument} onChange={(event) => { setSelectedDocument(event.target.value); setOffset(0); }}>
                  <option value="">All documents</option>
                  {documents.map((document) => <option key={document}>{document}</option>)}
                </select>
              </label>
            ) : null}
            <div className="viewer-text-size" aria-label="Text size">
              <span>Text size</span>
              <button type="button" onClick={() => setFontSize((size) => Math.max(14, size - 1))} disabled={fontSize === 14}>A−</button>
              <button type="button" onClick={() => setFontSize((size) => Math.min(22, size + 1))} disabled={fontSize === 22}>A+</button>
            </div>
          </div>
        </div>

        {loading ? <ProcessStatus messages={["Opening the manuscript..."]} /> : null}

        {!loading && passages.length ? (
          <div className="manuscript-pages" style={{ "--viewer-font-size": `${fontSize}px` } as CSSProperties}>
            {passages.map((passage) => (
              <article className="manuscript-passage" key={passage.chunk_id}>
                <header>
                  <div>
                    <span>{passage.document}</span>
                  </div>
                  <small>Paragraphs {passage.paragraph_start ?? "?"}-{passage.paragraph_end ?? "?"}</small>
                </header>
                <p><HighlightedText text={passage.text} query={search} /></p>
              </article>
            ))}
          </div>
        ) : null}

        {!loading && !passages.length ? <p className="empty-state">No manuscript text was found.</p> : null}

        <footer className="viewer-pagination">
          <button className="small-button" disabled={loading || offset === 0} onClick={() => setOffset((value) => Math.max(0, value - VIEWER_PAGE_SIZE))}>
            Previous
          </button>
          <form onSubmit={jumpToPage}>
            <span>Page</span>
            <input aria-label="Page number" inputMode="numeric" value={pageInput} onChange={(event) => setPageInput(event.target.value)} />
            <span>of {pageCount}</span>
          </form>
          <button className="small-button" disabled={loading || offset + VIEWER_PAGE_SIZE >= total} onClick={() => setOffset((value) => value + VIEWER_PAGE_SIZE)}>
            Next
          </button>
        </footer>
      </section>
    </section>
  );
}

function HighlightedText({ text, query }: { text: string; query: string }) {
  if (!query) return <>{text}</>;
  const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${escapedQuery})`, "gi"));
  return (
    <>
      {parts.map((part, index) =>
        part.toLocaleLowerCase() === query.toLocaleLowerCase() ? <mark key={index}>{part}</mark> : part
      )}
    </>
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
  const [displayGroups, setDisplayGroups] = useState<DisplayGroup[]>([]);
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
      setDisplayGroups(result.display_groups);
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
        {loading ? <ProcessStatus messages={QUESTION_STEPS} /> : null}
      </form>

      <OutputBlock title="Answer" body={answer} empty="No answer yet." sources={sources} />
      <DisplayGroups title="Sources" groups={displayGroups} />
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
  const [displayGroups, setDisplayGroups] = useState<DisplayGroup[]>([]);
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
      setDisplayGroups(result.display_groups);
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
          {loadingTerms ? <ProcessStatus messages={CANDIDATE_TERM_STEPS} /> : null}
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
            {generating ? <ProcessStatus messages={INDEX_ENTRY_STEPS} /> : null}
          </form>

          <OutputBlock title="Candidate entry" body={entry} empty="No entry yet." sources={sources} />

          <form className="index-search" onSubmit={submitIndexSearch}>
            <label>
              <span>Search existing index</span>
              <input value={indexSearch} onChange={(event) => setIndexSearch(event.target.value)} />
            </label>
            <button className="small-button" disabled={searching || !project.stats.existing_index_chunks}>
              {searching ? <Loader2 size={15} className="spin" /> : <Search size={15} />}
              Search
            </button>
            {searching ? <ProcessStatus messages={INDEX_SEARCH_STEPS} /> : null}
          </form>

          <DisplayGroups title="Manuscript sources" groups={displayGroups} />
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

function OutputBlock({ title, body, empty, sources = [] }: { title: string; body: string; empty: string; sources?: SourceChunk[] }) {
  return (
    <section className="output-block">
      <div className="panel-title">
        <h2>{title}</h2>
        <BookOpen size={17} />
      </div>
      {body ? <pre><CitationText body={body} sources={sources} /></pre> : <p className="empty-state">{empty}</p>}
    </section>
  );
}

function CitationText({ body, sources }: { body: string; sources: SourceChunk[] }) {
  if (!sources.length) return <>{body}</>;
  const sourceByNumber = new Map(sources.map((source) => [source.source_number, source]));
  const parts = body.split(/(\[Source \d+(?:, Source \d+)*\])/g);

  return (
    <>
      {parts.map((part, index) => {
        if (!/^\[Source \d+(?:, Source \d+)*\]$/.test(part)) return part;

        const sourceNumbers = [...part.matchAll(/Source (\d+)/g)].map((match) => Number(match[1]));
        const citedSources = sourceNumbers.map((sourceNumber) => sourceByNumber.get(sourceNumber));
        if (citedSources.some((source) => !source)) return part;

        const resolvedSources = citedSources as SourceChunk[];
        const firstSource = resolvedSources[0];
        const excerptText = firstSource.text.replace(/\s+/g, " ").trim();
        const excerpt = excerptText.slice(0, 220);
        const humanLabels = resolvedSources.map((source) => source.citation_label).join("; ");
        return (
          <button key={`${part}-${index}`} className="inline-citation" type="button" onClick={() => openSource(firstSource)}>
            [{humanLabels}]
            <span className="citation-preview" role="tooltip">{excerpt}{excerptText.length > 220 ? "…" : ""}</span>
          </button>
        );
      })}
    </>
  );
}

function sourceAnchor(source: SourceChunk) {
  return `source-${source.chunk_ids.join("-").replace(/[^a-z0-9_-]/gi, "-")}`;
}

function openSource(source: SourceChunk) {
  const element = document.querySelector<HTMLElement>(
    `[data-source-numbers~="${source.source_number}"]`
  ) ?? document.getElementById(sourceAnchor(source));
  if (element instanceof HTMLDetailsElement) element.open = true;
  element?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function DisplayGroups({ title, groups }: { title: string; groups: DisplayGroup[] }) {
  const sourceCount = groups.reduce((count, group) => count + group.source_numbers.length, 0);

  return (
    <section className="sources-block">
      <div className="panel-title">
        <h2>{title}</h2>
        <span>{sourceCount}</span>
      </div>
      {groups.length ? (
        <div className="source-stack">
          {groups.map((group) => {
            const sourceNumbers = group.source_numbers.join(" ");
            const sourceLabel = group.source_numbers.map((sourceNumber) => `Source ${sourceNumber}`).join(", ");
            return (
              <details
                key={sourceNumbers}
                className="source-card"
                data-source-numbers={sourceNumbers}
              >
                <summary>
                  <strong>{group.citation_labels.join("; ")}</strong>
                  <span>{sourceLabel}</span>
                </summary>
                <div className="source-card-body">
                  <p>{group.text}</p>
                  <button
                    className="copy-reference"
                    type="button"
                    onClick={() => navigator.clipboard.writeText(sourceLabel)}
                  >
                    <Copy size={14} />
                    Copy source reference
                  </button>
                </div>
              </details>
            );
          })}
        </div>
      ) : (
        <p className="empty-state">No sources.</p>
      )}
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
            <details id={sourceAnchor(source)} key={sourceAnchor(source)} className="source-card">
              <summary>
                <strong>{source.citation_label}</strong>
                <span>{source.document}</span>
              </summary>
              <div className="source-card-body">
                <p>{source.text}</p>
                <button className="copy-reference" type="button" onClick={() => navigator.clipboard.writeText(source.chunk_ids.join(", "))}>
                  <Copy size={14} />
                  Copy internal reference
                </button>
              </div>
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
