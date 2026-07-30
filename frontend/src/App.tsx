import {
  AlertCircle,
  Archive,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  CircleDollarSign,
  Copy,
  ExternalLink,
  FileSearch,
  FileText,
  Library,
  ListTree,
  Loader2,
  MessageCircle,
  Plus,
  RotateCcw,
  Save,
  Search,
  Send,
  SlidersHorizontal,
  Upload,
  X
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode, RefObject } from "react";
import {
  AppConfig,
  ApiRequestError,
  AnswerFacets,
  AnswerStrategy,
  AnswerVoice,
  AnswerWorldview,
  CandidateTerm,
  CostSettings,
  CostSummary,
  DEFAULT_ANSWER_FACETS,
  DEFAULT_ANSWER_STRATEGY,
  DisplayGroup,
  HistoriographicalLens,
  Project,
  PublicSource,
  SourceChunk,
  SourceReference,
  askQuestion,
  createProject,
  embedProject,
  generateIndexEntry,
  getCandidateTerms,
  getAppConfig,
  getCostSettings,
  getCostSummary,
  getManuscriptSources,
  searchExistingIndex,
  updateCostSettings
} from "./api";
import { VibeControl } from "./VibeControl";
import coverArt from "./assets/cradle-of-the-empire-cover.jpg";
import openingQuestions from "./openingQuestions.json";

type AppStage = "loading" | "unavailable" | "question";
type Notice = { type: "error" | "success" | "info"; text: string } | null;

type FacetOption<T extends string> = {
  value: T;
  label: string;
  description: string;
};

type GuidedStartIntent = "person" | "event" | "theme" | "passage";

type OpeningQuestion = {
  label: string;
  question: string;
};

type GuidedStartChoice = {
  label: string;
  description: string;
  template: string;
};

type GuidedStartRoute = {
  label: string;
  description: string;
  followUp: string;
  choices: ReadonlyArray<GuidedStartChoice>;
};

const OPENING_QUESTIONS: ReadonlyArray<OpeningQuestion> = openingQuestions;

const GUIDED_START_ROUTES: Record<GuidedStartIntent, GuidedStartRoute> = {
  person: {
    label: "A person",
    description: "Understand someone’s role, choices, or place in the larger story.",
    followUp: "What would you like to understand about this person?",
    choices: [
      {
        label: "A concise account",
        description: "Start with who they were and what they did.",
        template: "Who was [person], and what did they do?"
      },
      {
        label: "Why they matter",
        description: "Connect their actions to the manuscript’s larger story.",
        template: "Why does [person] matter to the manuscript's larger argument?"
      },
      {
        label: "How the book portrays them",
        description: "Examine the manuscript’s interpretation and evidence.",
        template: "How does the manuscript portray [person], and what evidence supports that portrayal?"
      }
    ]
  },
  event: {
    label: "An event or system",
    description: "Work out how something operated, happened, or changed.",
    followUp: "What kind of explanation would be most useful?",
    choices: [
      {
        label: "How it worked",
        description: "Get a direct explanation of the mechanics.",
        template: "How did [event or system] work?"
      },
      {
        label: "Causes and consequences",
        description: "Follow what produced it and what followed.",
        template: "How does the manuscript explain the causes and consequences of [event or system]?"
      },
      {
        label: "Why it matters",
        description: "Place it in the book’s larger historical argument.",
        template: "Why does [event or system] matter to the book's larger story?"
      }
    ]
  },
  theme: {
    label: "An argument or theme",
    description: "Follow an idea, tension, or claim through the manuscript.",
    followUp: "How would you like to follow this idea?",
    choices: [
      {
        label: "Clarify the idea",
        description: "Begin with what the manuscript means by it.",
        template: "What does the manuscript mean by [idea or theme]?"
      },
      {
        label: "Trace it through the book",
        description: "Connect evidence from more than one part of the story.",
        template: "How does the manuscript develop [idea or theme] across the book?"
      },
      {
        label: "Look for change over time",
        description: "Compare how the idea appears in different periods.",
        template: "How does [idea or theme] change between different periods in the manuscript?"
      }
    ]
  },
  passage: {
    label: "A passage or topic",
    description: "Find where the book discusses something and what it says.",
    followUp: "What should Archivist do with this topic?",
    choices: [
      {
        label: "Locate and explain it",
        description: "Find the relevant passages and summarize them.",
        template: "Where does the manuscript discuss [topic], and what does it say there?"
      },
      {
        label: "Synthesize its claims",
        description: "Bring the manuscript’s main points together.",
        template: "What are the manuscript's main claims about [topic]?"
      },
      {
        label: "Add historical context",
        description: "Connect the topic to the wider story told by the book.",
        template: "How does the manuscript place [topic] in its wider historical context?"
      }
    ]
  }
};

const LENS_OPTIONS: ReadonlyArray<FacetOption<HistoriographicalLens>> = [
  {
    value: "evidence_first",
    label: "Evidence-first",
    description: "Organizes the answer around the strongest support in the manuscript."
  },
  {
    value: "triumphalist",
    label: "Triumphalist",
    description: "Emphasizes achievement, confidence, expansion, and success."
  },
  {
    value: "tragic",
    label: "Tragic",
    description: "Emphasizes loss, contingency, conflict, and human cost."
  }
];

const VOICE_OPTIONS: ReadonlyArray<FacetOption<AnswerVoice>> = [
  {
    value: "scholarly",
    label: "Scholarly",
    description: "Uses the measured historical prose of the neutral baseline."
  },
  {
    value: "plainspoken",
    label: "Plainspoken",
    description: "Uses direct, accessible language with minimal ornament."
  },
  {
    value: "romantic",
    label: "Romantic",
    description: "Uses evocative language attentive to atmosphere, character, and drama."
  }
];

const WORLDVIEW_OPTIONS: ReadonlyArray<FacetOption<AnswerWorldview>> = [
  {
    value: "none",
    label: "None",
    description: "Adds no moral or metaphysical frame beyond the evidence-first baseline."
  },
  {
    value: "pious",
    label: "Pious / providential",
    description: "Attends to faith, providence, duty, and moral consequence."
  },
  {
    value: "secular_humanist",
    label: "Secular humanist",
    description: "Emphasizes human agency, dignity, institutions, and material consequence."
  },
  {
    value: "enlightenment_rationalist",
    label: "Enlightenment rationalist",
    description: "Emphasizes reason, inquiry, reform, and skepticism toward inherited claims."
  }
];

function facetOption<T extends string>(options: ReadonlyArray<FacetOption<T>>, value: T) {
  return options.find((option) => option.value === value) ?? options[0];
}

function answerFacetSummary(facets: AnswerFacets) {
  if (
    facets.historiographicalLens === DEFAULT_ANSWER_FACETS.historiographicalLens
    && facets.voice === DEFAULT_ANSWER_FACETS.voice
    && facets.worldview === DEFAULT_ANSWER_FACETS.worldview
  ) {
    return "Neutral baseline";
  }
  return [
    facetOption(LENS_OPTIONS, facets.historiographicalLens).label,
    facetOption(VOICE_OPTIONS, facets.voice).label,
    facetOption(WORLDVIEW_OPTIONS, facets.worldview).label
  ].join(" · ");
}

function compactAnswerFacetSummary(facets: AnswerFacets) {
  const summary = answerFacetSummary(facets);
  return summary === "Neutral baseline" ? "Neutral" : summary;
}

function hasInterpretiveFrame(facets: AnswerFacets) {
  return (
    facets.historiographicalLens
      !== DEFAULT_ANSWER_FACETS.historiographicalLens
    || facets.worldview !== DEFAULT_ANSWER_FACETS.worldview
  );
}

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
      <span className="sr-only">{messages[0]}</span>
      <span aria-hidden="true">{messages[messageIndex]}</span>
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
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [appConfig, setAppConfig] = useState<AppConfig | null>(null);
  const [stage, setStage] = useState<AppStage>("loading");
  const [notice, setNotice] = useState<Notice>(null);

  useEffect(() => {
    getAppConfig()
      .then((config) => {
        const builtInProject = config.project;
        const ready = builtInProject
          && builtInProject.stats.searchable_chunks > 0
          && builtInProject.embedded
          && builtInProject.embedded_chunks === builtInProject.stats.searchable_chunks;

        if (!builtInProject || !ready) {
          setActiveProject(builtInProject ?? null);
          setStage("unavailable");
          setNotice({
            type: "error",
            text: "The local Cradle of the Empire corpus or its search index is unavailable."
          });
          return;
        }

        setAppConfig(config);
        setActiveProject(builtInProject);
        setStage("question");
      })
      .catch((error) => {
        setStage("unavailable");
        setNotice({ type: "error", text: errorMessage(error) });
      });
  }, []);

  return (
    <main className="library-shell">
      <div className="library-grain" />
      {stage !== "question" ? (
        <header className="app-header">
          <div className="brand-mark">
            <Library size={25} />
            <span>Archivist</span>
          </div>
        </header>
      ) : null}

      {notice ? <NoticeBanner notice={notice} onClose={() => setNotice(null)} /> : null}

      {stage === "loading" ? (
        <section className="welcome-stage">
          <ProcessStatus messages={["Opening Cradle of the Empire..."]} />
        </section>
      ) : null}

      {stage === "unavailable" ? (
        <section className="welcome-stage">
          <div className="manuscript-desk">
            <div className="desk-intro">
              <p className="kicker">Built-in manuscript</p>
              <h1>Cradle of the Empire is not ready.</h1>
              <p>Restore or rebuild the local corpus and Chroma search index, then reload Archivist.</p>
            </div>
          </div>
        </section>
      ) : null}

      {stage === "question" && activeProject && appConfig ? (
        <QuestionMode config={appConfig} project={activeProject} setNotice={setNotice} />
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

type ChatTurnStatus = "pending" | "complete" | "error";

type ChatTurn = {
  id: string;
  question: string;
  facets: AnswerFacets;
  // What was requested, and what the server reports actually ran. They differ if
  // a request is rejected, so the badge reads the second one.
  requestedStrategy: AnswerStrategy;
  answerStrategy?: AnswerStrategy;
  status: ChatTurnStatus;
  answer: string;
  answerStatus?: string;
  resolvedQuery?: string;
  sources: SourceReference[];
  displayGroups: DisplayGroup[];
  error?: string;
  validationErrorCode?: string;
  stageTimingsMs?: Record<string, number>;
  budgetBlocked?: boolean;
  turnCostUsd?: number;
};

function isPublicSource(source: SourceReference): source is PublicSource {
  return "kind" in source && source.kind === "public_locator";
}

function splitInterpretiveAnswer(turn: ChatTurn) {
  const framed = turn.answerStatus === "answered"
    && hasInterpretiveFrame(turn.facets);
  const paragraphs = turn.answer.split(/\n{2,}/);
  if (!framed || paragraphs.length < 3) return null;
  return {
    preface: paragraphs[0],
    evidence: paragraphs.slice(1, -1).join("\n\n"),
    coda: paragraphs[paragraphs.length - 1]
  };
}

function answerForConversationHistory(turn: ChatTurn) {
  return splitInterpretiveAnswer(turn)?.evidence ?? turn.answer;
}

function createClientId(prefix: "turn" | "conversation") {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function createTurnId() {
  return createClientId("turn");
}

function createConversationId() {
  return createClientId("conversation");
}

const DEFAULT_COST_SETTINGS: CostSettings = {
  monthly_budget_usd: null,
  warning_threshold_percent: 80,
  hard_limit_enabled: false
};

function formatUsd(value: number) {
  if (value === 0) return "$0.00";
  const absolute = Math.abs(value);
  if (absolute > 0 && absolute < 0.0001) return value < 0 ? "−<$0.0001" : "<$0.0001";
  if (absolute < 0.01) return `$${value.toFixed(4)}`;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

function formatTurnCost(value: number) {
  if (value > 0 && value < 0.0001) return "<$0.0001";
  return value < 1 ? `$${value.toFixed(4)}` : formatUsd(value);
}

function formatCostTimestamp(timestamp: string) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC"
  }).format(date) + " UTC";
}

function operationLabel(operation: string) {
  return operation
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toLocaleUpperCase());
}

function CostMeterButton({
  summary,
  loading,
  open,
  onOpen
}: {
  summary: CostSummary | null;
  loading: boolean;
  open: boolean;
  onOpen: () => void;
}) {
  const budget = summary?.budget;
  const percent = budget?.percent_used;
  const state = budget?.exceeded ? "is-exceeded" : budget?.warning ? "is-warning" : "";
  const status = !summary
    ? loading ? "Loading cost ledger" : "Cost ledger unavailable"
    : budget?.monthly_budget_usd === null
      ? `${formatUsd(summary.month_usd)} this month; no local budget set`
      : `${formatUsd(summary.month_usd)} this month; ${Math.round(percent ?? 0)} percent of local budget`;

  return (
    <button
      type="button"
      className={`cost-meter ${state}`}
      aria-label={`Open cost ledger. ${status}.`}
      aria-haspopup="dialog"
      aria-expanded={open}
      aria-controls="archivist-cost-ledger"
      onClick={onOpen}
    >
      {budget?.warning || budget?.exceeded
        ? <AlertCircle size={16} aria-hidden="true" />
        : <CircleDollarSign size={16} aria-hidden="true" />}
      <span className="cost-meter-copy">
        <small>This month</small>
        <strong>{summary ? formatUsd(summary.month_usd) : loading ? "Loading…" : "Unavailable"}</strong>
      </span>
      {budget?.monthly_budget_usd !== null && percent !== null && percent !== undefined ? (
        <span className="cost-meter-track" aria-hidden="true">
          <i style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
        </span>
      ) : null}
    </button>
  );
}

type CostSettingsSaveState = "idle" | "saving" | "success" | "error";

function CostLedgerDrawer({
  open,
  summary,
  loading,
  error,
  onClose,
  onRefresh
}: {
  open: boolean;
  summary: CostSummary | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onRefresh: () => Promise<void>;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [settings, setSettings] = useState<CostSettings | null>(null);
  const [settingsDraft, setSettingsDraft] = useState<CostSettings>({ ...DEFAULT_COST_SETTINGS });
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSaveState, setSettingsSaveState] = useState<CostSettingsSaveState>("idle");
  const [settingsSaveMessage, setSettingsSaveMessage] = useState("");

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  async function loadSettings() {
    setSettingsLoading(true);
    setSettingsError(null);
    try {
      const loaded = await getCostSettings();
      setSettings(loaded);
      setSettingsDraft({ ...loaded });
    } catch (loadError) {
      setSettingsError(errorMessage(loadError));
    } finally {
      setSettingsLoading(false);
    }
  }

  useEffect(() => {
    void loadSettings();
  }, []);

  function updateSettingsDraft(next: CostSettings) {
    setSettingsDraft(next);
    setSettingsSaveState("idle");
    setSettingsSaveMessage("");
  }

  async function saveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSettingsSaveState("saving");
    setSettingsSaveMessage("");
    try {
      const saved = await updateCostSettings({
        ...settingsDraft,
        hard_limit_enabled: settingsDraft.monthly_budget_usd === null
          ? false
          : settingsDraft.hard_limit_enabled
      });
      setSettings(saved);
      setSettingsDraft({ ...saved });
      setSettingsSaveState("success");
      setSettingsSaveMessage("Budget settings saved.");
      await onRefresh();
    } catch (saveError) {
      setSettingsSaveState("error");
      setSettingsSaveMessage(errorMessage(saveError));
    }
  }

  const budget = summary?.budget;
  const budgetPercent = budget?.percent_used;
  const trackingStarted = summary?.tracking_started_at
    ? formatCostTimestamp(summary.tracking_started_at)
    : null;

  return (
    <dialog
      ref={dialogRef}
      id="archivist-cost-ledger"
      className="cost-ledger-dialog"
      aria-labelledby="cost-ledger-title"
      aria-describedby="cost-ledger-authority-note"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="cost-ledger-drawer">
        <header className="cost-ledger-header">
          <div>
            <span>Live cost ledger</span>
            <h2 id="cost-ledger-title">Usage &amp; budget</h2>
          </div>
          <button ref={closeButtonRef} type="button" aria-label="Close cost ledger" onClick={onClose}>
            <X size={18} />
          </button>
        </header>

        <div className="cost-ledger-content">
          {loading && !summary ? (
            <div className="cost-ledger-loading" role="status">
              <Loader2 size={18} className="spin" />
              Reading the local ledger…
            </div>
          ) : null}

          {error ? (
            <div className="cost-ledger-error" role="alert">
              <AlertCircle size={17} />
              <span>{error}</span>
              <button type="button" onClick={() => void onRefresh()}>Try again</button>
            </div>
          ) : null}

          {summary ? (
            <>
              <section className="cost-overview" aria-labelledby="cost-overview-title">
                <div className="cost-section-heading">
                  <span>Estimated spend</span>
                  <h3 id="cost-overview-title">At a glance</h3>
                </div>
                <dl className="cost-total-grid">
                  <div>
                    <dt>This conversation</dt>
                    <dd>{formatUsd(summary.conversation_usd)}</dd>
                  </div>
                  <div>
                    <dt>This month <small>UTC</small></dt>
                    <dd>{formatUsd(summary.month_usd)}</dd>
                  </div>
                  <div>
                    <dt>All time</dt>
                    <dd>{formatUsd(summary.all_time_usd)}</dd>
                  </div>
                </dl>
                {budget?.monthly_budget_usd !== null ? (
                  <div className={`cost-budget-progress${budget?.warning ? " is-warning" : ""}${budget?.exceeded ? " is-exceeded" : ""}`}>
                    <div>
                      <span>Local monthly budget</span>
                      <strong>
                        {Math.round(budgetPercent ?? 0)}% of {formatUsd(budget?.monthly_budget_usd ?? 0)}
                      </strong>
                    </div>
                    <progress max={100} value={Math.min(100, Math.max(0, budgetPercent ?? 0))}>
                      {Math.round(budgetPercent ?? 0)}%
                    </progress>
                    <small>
                      {budget?.exceeded
                        ? "Budget exceeded"
                        : budget?.remaining_usd !== null
                          ? `${formatUsd(budget?.remaining_usd ?? 0)} remaining`
                          : "Remaining amount unavailable"}
                    </small>
                  </div>
                ) : (
                  <p className="cost-no-budget">No local monthly budget is set.</p>
                )}
              </section>

              <section className="cost-ledger-section" aria-labelledby="cost-operations-title">
                <div className="cost-section-heading">
                  <span>Where it went</span>
                  <h3 id="cost-operations-title">Operation breakdown</h3>
                </div>
                {summary.operations.length ? (
                  <dl className="cost-operation-list">
                    {summary.operations.map((operation) => (
                      <div key={operation.operation}>
                        <dt>{operationLabel(operation.operation)}</dt>
                        <dd>
                          <span>{operation.calls.toLocaleString()} {operation.calls === 1 ? "call" : "calls"}</span>
                          <span>{operation.tokens.toLocaleString()} tokens</span>
                          <strong>{formatUsd(operation.cost_usd)}</strong>
                        </dd>
                      </div>
                    ))}
                  </dl>
                ) : <p className="cost-ledger-empty">No priced operations yet.</p>}
              </section>

              <section className="cost-ledger-section" aria-labelledby="cost-events-title">
                <div className="cost-section-heading">
                  <span>Latest activity</span>
                  <h3 id="cost-events-title">Recent calls</h3>
                </div>
                {summary.recent_events.length ? (
                  <ol className="cost-event-list">
                    {summary.recent_events.map((costEvent, index) => (
                      <li key={`${costEvent.timestamp}-${costEvent.operation}-${index}`}>
                        <div>
                          <strong>{operationLabel(costEvent.operation)}</strong>
                          <span>{costEvent.model}</span>
                        </div>
                        <div>
                          <strong>{costEvent.cost_usd === null ? "Unpriced" : formatUsd(costEvent.cost_usd)}</strong>
                          <span>{costEvent.tokens.toLocaleString()} tokens · {formatCostTimestamp(costEvent.timestamp)}</span>
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : <p className="cost-ledger-empty">No calls recorded yet.</p>}
              </section>

              <div className="cost-ledger-provenance">
                <p>
                  Totals begin when local tracking was enabled{trackingStarted ? ` (${trackingStarted})` : ""};
                  earlier OpenAI spend was not backfilled. Monthly periods use UTC.
                </p>
                <p>
                  Pricing {summary.pricing_version || "version unavailable"} · {summary.unpriced_events.toLocaleString()} unpriced {summary.unpriced_events === 1 ? "event" : "events"}.
                </p>
              </div>
            </>
          ) : null}

          <section className="cost-ledger-section cost-settings-section" aria-labelledby="cost-settings-title">
            <div className="cost-section-heading">
              <span>Guardrails</span>
              <h3 id="cost-settings-title">Local budget controls</h3>
            </div>
            <p className="cost-settings-explainer">
              OpenAI project budgets are soft alerts. This local hard stop blocks the next Archivist request
              after the limit is reached; it does not change OpenAI billing controls.
            </p>

            {settingsError ? (
              <div className="cost-settings-message is-error" role="alert">
                <span>{settingsError}</span>
                <button type="button" onClick={() => void loadSettings()}>Reload</button>
              </div>
            ) : null}

            {settingsLoading && !settings ? (
              <div className="cost-ledger-loading" role="status">
                <Loader2 size={16} className="spin" />
                Loading budget settings…
              </div>
            ) : (
              <form className="cost-settings-form" onSubmit={saveSettings}>
                <label>
                  <span>Monthly budget (USD)</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    min="0.01"
                    max="100000"
                    step="0.01"
                    placeholder="No budget"
                    value={settingsDraft.monthly_budget_usd ?? ""}
                    disabled={settingsSaveState === "saving"}
                    onChange={(event) => {
                      const value = event.currentTarget.value;
                      updateSettingsDraft({
                        ...settingsDraft,
                        monthly_budget_usd: value === "" ? null : Number(value),
                        hard_limit_enabled: value === "" ? false : settingsDraft.hard_limit_enabled
                      });
                    }}
                  />
                </label>
                <label>
                  <span>Warn at</span>
                  <span className="cost-percent-input">
                    <input
                      type="number"
                      inputMode="numeric"
                      min="1"
                      max="100"
                      step="1"
                      required
                      value={settingsDraft.warning_threshold_percent}
                      disabled={settingsSaveState === "saving"}
                      onChange={(event) => updateSettingsDraft({
                        ...settingsDraft,
                        warning_threshold_percent: Number(event.currentTarget.value)
                      })}
                    />
                    <i aria-hidden="true">%</i>
                  </span>
                </label>
                <label className="cost-hard-stop-toggle">
                  <input
                    type="checkbox"
                    checked={settingsDraft.hard_limit_enabled}
                    disabled={settingsDraft.monthly_budget_usd === null || settingsSaveState === "saving"}
                    onChange={(event) => updateSettingsDraft({
                      ...settingsDraft,
                      hard_limit_enabled: event.currentTarget.checked
                    })}
                  />
                  <span>
                    <strong>Hard stop</strong>
                    <small>{settingsDraft.monthly_budget_usd === null ? "Set a budget to enable" : "Block the next request at the limit"}</small>
                  </span>
                </label>
                <div className="cost-settings-submit">
                  <button type="submit" disabled={settingsSaveState === "saving" || settingsLoading}>
                    {settingsSaveState === "saving" ? <Loader2 size={15} className="spin" /> : <Save size={15} />}
                    {settingsSaveState === "saving" ? "Saving…" : "Save"}
                  </button>
                  {settingsSaveMessage ? (
                    <span
                      className={settingsSaveState === "error" ? "is-error" : "is-success"}
                      role={settingsSaveState === "error" ? "alert" : "status"}
                    >
                      {settingsSaveMessage}
                    </span>
                  ) : null}
                </div>
              </form>
            )}
          </section>

          <footer className="cost-ledger-footer" id="cost-ledger-authority-note">
            <strong>Local estimate; OpenAI billing is authoritative.</strong>
            <a href="https://platform.openai.com/usage" target="_blank" rel="noreferrer">
              Open OpenAI usage
              <ExternalLink size={14} />
            </a>
          </footer>
        </div>
      </div>
    </dialog>
  );
}

function NewConversationButton({
  pending,
  onStart
}: {
  pending: boolean;
  onStart: () => void;
}) {
  return (
    <button
      type="button"
      className="new-conversation-button"
      disabled={pending}
      aria-label="Start a new conversation"
      title="Start a new conversation"
      onClick={onStart}
    >
      <Plus size={15} aria-hidden="true" />
      <span className="new-conversation-label-full">Start new conversation</span>
      <span className="new-conversation-label-short" aria-hidden="true">New</span>
    </button>
  );
}

function OpeningGuidance({
  selectedQuestion,
  onPrepareQuestion,
  onFocusQuestion
}: {
  selectedQuestion: string;
  onPrepareQuestion: (question: string, selectPlaceholder?: boolean) => void;
  onFocusQuestion: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [intent, setIntent] = useState<GuidedStartIntent | null>(null);
  const guideTriggerRef = useRef<HTMLButtonElement>(null);
  const guideQuestionRef = useRef<HTMLHeadingElement>(null);
  const route = intent ? GUIDED_START_ROUTES[intent] : null;

  useEffect(() => {
    if (!open) return;
    window.requestAnimationFrame(() => guideQuestionRef.current?.focus({ preventScroll: true }));
  }, [intent, open]);

  function closeGuide(focusTrigger = true) {
    setOpen(false);
    setIntent(null);
    if (focusTrigger) {
      window.requestAnimationFrame(() => guideTriggerRef.current?.focus({ preventScroll: true }));
    }
  }

  if (open) {
    return (
      <section className="guided-start" aria-labelledby="guided-start-question">
        <header className="guided-start-header">
          <div className="guided-start-identity">
            <span><Library size={15} aria-hidden="true" /></span>
            <div>
              <strong>Archivist</strong>
              <small>Let’s shape a useful first question</small>
            </div>
          </div>
          <button type="button" aria-label="Close guided start" onClick={() => closeGuide()}>
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        {route ? (
          <div className="guided-start-step">
            <button
              type="button"
              className="guided-start-back"
              onClick={() => setIntent(null)}
            >
              <ArrowLeft size={14} aria-hidden="true" />
              Back
            </button>
            <p>You chose {route.label.toLowerCase()}</p>
            <h2 id="guided-start-question" ref={guideQuestionRef} tabIndex={-1}>
              {route.followUp}
            </h2>
            <ul className="guided-start-options">
              {route.choices.map((choice) => (
                <li key={choice.label}>
                  <button
                    type="button"
                    onClick={() => {
                      closeGuide(false);
                      onPrepareQuestion(choice.template, true);
                    }}
                  >
                    <strong>{choice.label}</strong>
                    <span>{choice.description}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="guided-start-step">
            <p>One quick question</p>
            <h2 id="guided-start-question" ref={guideQuestionRef} tabIndex={-1}>
              What are you hoping to explore?
            </h2>
            <ul className="guided-start-options is-intent-list">
              {(Object.entries(GUIDED_START_ROUTES) as Array<
                [GuidedStartIntent, GuidedStartRoute]
              >).map(([routeId, routeOption]) => (
                <li key={routeId}>
                  <button type="button" onClick={() => setIntent(routeId)}>
                    <strong>{routeOption.label}</strong>
                    <span>{routeOption.description}</span>
                  </button>
                </li>
              ))}
            </ul>
            <button
              type="button"
              className="guided-start-direct"
              onClick={() => {
                closeGuide(false);
                onFocusQuestion();
              }}
            >
              I already have a question
            </button>
          </div>
        )}
      </section>
    );
  }

  return (
    <section className="opening-suggestions" aria-labelledby="opening-suggestions-title">
      <p id="opening-suggestions-title">Or start here</p>
      <div>
        {OPENING_QUESTIONS.map((starter) => (
          <button
            type="button"
            key={starter.label}
            aria-pressed={selectedQuestion === starter.question}
            onClick={() => onPrepareQuestion(starter.question)}
          >
            <span>{starter.label}</span>
            <strong>{starter.question}</strong>
          </button>
        ))}
        <button
          ref={guideTriggerRef}
          type="button"
          className="opening-guide-trigger"
          onClick={() => setOpen(true)}
        >
          <MessageCircle size={15} aria-hidden="true" />
          <span>
            <small>Not sure what to ask?</small>
            <strong>Let Archivist guide me</strong>
          </span>
        </button>
      </div>
    </section>
  );
}

function NewConversationSummary({
  projectName
}: {
  projectName: string;
}) {
  return (
    <div className="chat-open-summary">
      <p className="chat-kicker">Conversation in progress</p>
      <h1 id="question-page-title">Your thread is open.</h1>
      <p>
        Continue below with <cite>{projectName}</cite>, or use Start new conversation above
        to begin again.
      </p>
      <a href="#conversation-thread-start">
        <MessageCircle size={15} aria-hidden="true" />
        Continue conversation
      </a>
    </div>
  );
}

function QuestionMode({
  config,
  project,
  setNotice
}: {
  config: AppConfig;
  project: Project;
  setNotice: (notice: Notice) => void;
}) {
  const publicDemo = config.exposure_profile === "public_demo";
  const [question, setQuestion] = useState("");
  const [facets, setFacets] = useState<AnswerFacets>({ ...DEFAULT_ANSWER_FACETS });
  // Per-turn, exactly like the interpretive facets, so a reader can compare the
  // two scopes inside one conversation instead of starting a new thread.
  const [answerStrategy, setAnswerStrategy] = useState<AnswerStrategy>(DEFAULT_ANSWER_STRATEGY);
  const fullContextAvailable = config.features.full_context_answers === true;
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [copiedTurnId, setCopiedTurnId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState(createConversationId);
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);
  const [costSummaryLoading, setCostSummaryLoading] = useState(config.features.cost_ledger);
  const [costSummaryError, setCostSummaryError] = useState<string | null>(null);
  const [costDrawerOpen, setCostDrawerOpen] = useState(false);
  const conversationRef = useRef<HTMLElement>(null);
  const landingQuestionRef = useRef<HTMLTextAreaElement>(null);
  const pending = turns.some((turn) => turn.status === "pending");
  const chatStarted = turns.length > 0;

  useEffect(() => {
    if (!config.features.cost_ledger) {
      setCostSummary(null);
      setCostSummaryLoading(false);
      setCostSummaryError(null);
      return;
    }
    let cancelled = false;
    setCostSummaryLoading(true);
    setCostSummaryError(null);
    getCostSummary(project.id, conversationId)
      .then((summary) => {
        if (!cancelled) setCostSummary(summary);
      })
      .catch((loadError) => {
        if (!cancelled) setCostSummaryError(errorMessage(loadError));
      })
      .finally(() => {
        if (!cancelled) setCostSummaryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [config.features.cost_ledger, conversationId, project.id]);

  async function refreshCostSummary() {
    if (!config.features.cost_ledger) return;
    setCostSummaryLoading(true);
    setCostSummaryError(null);
    try {
      setCostSummary(await getCostSummary(project.id, conversationId));
    } catch (loadError) {
      setCostSummaryError(errorMessage(loadError));
    } finally {
      setCostSummaryLoading(false);
    }
  }

  function scrollToTurn(turnId: string, firstTurn: boolean) {
    window.setTimeout(() => {
      const target = firstTurn
        ? conversationRef.current
        : document.getElementById(`turn-${turnId}`);
      if (!target) return;
      const behavior: ScrollBehavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth";
      target.scrollIntoView({ behavior, block: "start" });
    }, 80);
  }

  async function runTurn(
    turnId: string,
    turnQuestion: string,
    turnFacets: AnswerFacets,
    history: Array<{ question: string; answer: string }>,
    allowOverBudget = false,
    turnStrategy: AnswerStrategy = DEFAULT_ANSWER_STRATEGY
  ) {
    try {
      const result = await askQuestion(
        project.id,
        turnQuestion,
        5,
        turnFacets,
        history.slice(-6),
        {
          conversationId,
          turnId,
          allowOverBudget,
          publicDemo,
          answerStrategy: turnStrategy
        }
      );
      if (result.costs) setCostSummary(result.costs);
      else if (config.features.cost_ledger) void refreshCostSummary();
      const validationFailed = result.answer_status === "generation_contract_failed";
      const pipelineFailed = validationFailed || result.answer_status === "corpus_integrity_failed";
      setTurns((current) => current.map((turn) => turn.id === turnId ? {
        ...turn,
        status: pipelineFailed ? "error" : "complete",
        answer: pipelineFailed ? "" : result.answer,
        answerStatus: result.answer_status,
        answerStrategy: result.answer_strategy ?? DEFAULT_ANSWER_STRATEGY,
        resolvedQuery: result.resolved_query,
        facets: {
          historiographicalLens: result.historiographical_lens,
          voice: result.voice,
          worldview: result.worldview
        },
        sources: result.sources,
        displayGroups: result.display_groups ?? [],
        error: validationFailed
          ? "Relevant passages were found, but the generated response did not pass Archivist's evidence checks. No answer was presented as manuscript-grounded."
          : pipelineFailed
            ? result.answer
            : undefined,
        validationErrorCode: result.run_diagnostics?.validation_error_code ?? undefined,
        stageTimingsMs: result.run_diagnostics?.stage_timings_ms,
        budgetBlocked: false,
        turnCostUsd: result.costs?.turn_usd
      } : turn));
    } catch (error) {
      const budgetBlocked = error instanceof ApiRequestError && error.status === 402;
      setTurns((current) => current.map((turn) => turn.id === turnId ? {
        ...turn,
        status: "error",
        error: errorMessage(error),
        budgetBlocked
      } : turn));
      // A later call in the turn can fail after an earlier paid call succeeded.
      // Refresh on every failure so the ledger never looks artificially stale.
      if (config.features.cost_ledger) void refreshCostSummary();
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || pending) return;

    const history = turns
      .filter((turn) => turn.status === "complete")
      .slice(-6)
      .map((turn) => ({
        question: turn.question.slice(0, 4_000),
        answer: answerForConversationHistory(turn).slice(0, 12_000)
      }));
    const turnId = createTurnId();
    const firstTurn = turns.length === 0;
    const nextTurn: ChatTurn = {
      id: turnId,
      question: trimmedQuestion,
      facets: { ...facets },
      requestedStrategy: answerStrategy,
      status: "pending",
      answer: "",
      sources: [],
      displayGroups: [],
      budgetBlocked: false
    };

    setTurns((current) => [...current, nextTurn]);
    setQuestion("");
    scrollToTurn(turnId, firstTurn);
    await runTurn(turnId, trimmedQuestion, facets, history, false, answerStrategy);
  }

  async function retryTurn(turnId: string, allowOverBudget = false) {
    if (pending) return;
    const turnIndex = turns.findIndex((turn) => turn.id === turnId);
    const turn = turns[turnIndex];
    if (!turn) return;
    const history = turns
      .slice(0, turnIndex)
      .filter((candidate) => candidate.status === "complete")
      .slice(-6)
      .map((candidate) => ({
        question: candidate.question.slice(0, 4_000),
        answer: answerForConversationHistory(candidate).slice(0, 12_000)
      }));

    setTurns((current) => current.map((candidate) => candidate.id === turnId ? {
      ...candidate,
      status: "pending",
      error: undefined,
      answerStatus: undefined,
      validationErrorCode: undefined,
      stageTimingsMs: undefined,
      budgetBlocked: false
    } : candidate));
    scrollToTurn(turnId, false);
    await runTurn(
      turnId,
      turn.question,
      turn.facets,
      history,
      allowOverBudget,
      turn.requestedStrategy ?? DEFAULT_ANSWER_STRATEGY
    );
  }

  async function approveTurn(turnId: string) {
    const approved = window.confirm(
      "Approve one Archivist request above the local monthly budget? This does not change your saved limit."
    );
    if (!approved) return;
    await retryTurn(turnId, true);
  }

  async function copyAnswer(turn: ChatTurn) {
    try {
      await navigator.clipboard.writeText(turn.answer);
      setCopiedTurnId(turn.id);
      window.setTimeout(() => setCopiedTurnId((current) => current === turn.id ? null : current), 1800);
    } catch {
      setNotice({ type: "error", text: "The answer could not be copied." });
    }
  }

  function startNewConversation() {
    if (pending) return;
    setTurns([]);
    setQuestion("");
    setFacets({ ...DEFAULT_ANSWER_FACETS });
    setCopiedTurnId(null);
    setConversationId(createConversationId());
    setCostSummary(null);
    setCostSummaryError(null);
    const behavior: ScrollBehavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto"
      : "smooth";
    window.scrollTo({ top: 0, behavior });
    window.setTimeout(() => landingQuestionRef.current?.focus({ preventScroll: true }), 0);
  }

  function focusLandingQuestion(candidateQuestion = question, selectPlaceholder = false) {
    window.requestAnimationFrame(() => {
      const input = landingQuestionRef.current;
      if (!input) return;
      input.focus({ preventScroll: true });
      const placeholderStart = selectPlaceholder ? candidateQuestion.indexOf("[") : -1;
      const placeholderEnd = selectPlaceholder ? candidateQuestion.indexOf("]", placeholderStart) : -1;
      if (placeholderStart >= 0 && placeholderEnd > placeholderStart) {
        input.setSelectionRange(placeholderStart, placeholderEnd + 1);
      } else {
        input.setSelectionRange(candidateQuestion.length, candidateQuestion.length);
      }
      const bounds = input.getBoundingClientRect();
      if (bounds.top < 24 || bounds.bottom > window.innerHeight - 24) {
        const behavior: ScrollBehavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth";
        input.scrollIntoView({ behavior, block: "center" });
      }
    });
  }

  function prepareLandingQuestion(candidateQuestion: string, selectPlaceholder = false) {
    setQuestion(candidateQuestion);
    focusLandingQuestion(candidateQuestion, selectPlaceholder);
  }

  return (
    <section
      className={`chat-page${chatStarted ? " has-conversation" : ""}`}
      aria-labelledby="question-page-title"
    >
      <section className="chat-landing">
        <figure className="chat-cover-panel">
          <img
            src={coverArt}
            alt="Cover art for Cradle of the Empire: an ancient tree overlooking sailing ships"
            width="896"
            height="1344"
            decoding="async"
          />
          <span className="chat-cover-vignette" aria-hidden="true" />
          <figcaption>
            <span>Featured manuscript</span>
            <strong>{project.name}</strong>
          </figcaption>
        </figure>

        <div className="chat-intro-panel">
          <header className="chat-landing-header">
            <div className="chat-brand">
              <span><Library size={17} /></span>
              <strong>Archivist</strong>
              <i aria-hidden="true" />
              <small>Manuscript conversation</small>
            </div>
            {!chatStarted ? (
              <div className="chat-header-actions">
                {config.features.cost_ledger ? (
                  <CostMeterButton
                    summary={costSummary}
                    loading={costSummaryLoading}
                    open={costDrawerOpen}
                    onOpen={() => setCostDrawerOpen(true)}
                  />
                ) : null}
                <VibeControl />
              </div>
            ) : (
              <NewConversationButton pending={pending} onStart={startNewConversation} />
            )}
          </header>

          {!chatStarted ? (
            <div className="chat-start-hub">
              <div className="chat-intro-copy">
                <p className="chat-kicker">A conversation grounded in one manuscript</p>
                <h1 id="question-page-title">What would you like to uncover?</h1>
                <p className="chat-intro-description">
                  Ask <cite>{project.name}</cite> directly, or let Archivist help shape a
                  useful first question.
                </p>
              </div>
              <ConversationComposer
                location="landing"
                project={project}
                question={question}
                facets={facets}
                answerStrategy={answerStrategy}
                fullContextAvailable={fullContextAvailable}
                pending={pending}
                inputRef={landingQuestionRef}
                onQuestionChange={setQuestion}
                onFacetsChange={setFacets}
                onAnswerStrategyChange={setAnswerStrategy}
                onSubmit={submit}
              />
              <OpeningGuidance
                selectedQuestion={question}
                onPrepareQuestion={prepareLandingQuestion}
                onFocusQuestion={() => focusLandingQuestion()}
              />
              <p className="chat-evidence-caveat">
                Searches this manuscript · cites supporting passages · remembers follow-ups.
                Nothing is sent until you press Ask.
              </p>
            </div>
          ) : (
            <div className="chat-start-hub is-conversation-open">
              <NewConversationSummary projectName={project.name} />
            </div>
          )}
        </div>
      </section>

      {chatStarted ? (
        <section
          className="conversation-shell"
          id="conversation-thread-start"
          ref={conversationRef}
          aria-label="Conversation with Archivist"
        >
          <header className="conversation-header">
            <a className="conversation-brand" href="#question-page-title" aria-label="Return to the Archivist introduction">
              <span><Library size={16} /></span>
              <span>
                <strong>Archivist</strong>
                <small>{project.name}</small>
              </span>
            </a>
            <div className="conversation-actions">
              {config.features.cost_ledger ? (
                <CostMeterButton
                  summary={costSummary}
                  loading={costSummaryLoading}
                  open={costDrawerOpen}
                  onOpen={() => setCostDrawerOpen(true)}
                />
              ) : null}
              <NewConversationButton pending={pending} onStart={startNewConversation} />
              <VibeControl compact />
            </div>
          </header>

          <ol className="conversation-thread" aria-label="Conversation turns">
            {turns.map((turn, index) => (
              <li key={turn.id} className={`turn-list-item is-${turn.status}`}>
                <ConversationTurn
                  turn={turn}
                  turnNumber={index + 1}
                  copied={copiedTurnId === turn.id}
                  onCopy={() => copyAnswer(turn)}
                  onRetry={() => retryTurn(turn.id)}
                  onApprove={() => approveTurn(turn.id)}
                  publicDemo={publicDemo}
                />
              </li>
            ))}
          </ol>

          <div className="conversation-composer-dock">
            <ConversationComposer
              location="thread"
              project={project}
              question={question}
              facets={facets}
              answerStrategy={answerStrategy}
              fullContextAvailable={fullContextAvailable}
              pending={pending}
              onQuestionChange={setQuestion}
              onFacetsChange={setFacets}
              onAnswerStrategyChange={setAnswerStrategy}
              onSubmit={submit}
            />
          </div>
        </section>
      ) : null}

      {config.features.cost_ledger ? (
        <CostLedgerDrawer
          open={costDrawerOpen}
          summary={costSummary}
          loading={costSummaryLoading}
          error={costSummaryError}
          onClose={() => setCostDrawerOpen(false)}
          onRefresh={refreshCostSummary}
        />
      ) : null}
    </section>
  );
}

function ConversationComposer({
  location,
  project,
  question,
  facets,
  answerStrategy,
  fullContextAvailable,
  pending,
  inputRef,
  onQuestionChange,
  onFacetsChange,
  onAnswerStrategyChange,
  onSubmit
}: {
  location: "landing" | "thread";
  project: Project;
  question: string;
  facets: AnswerFacets;
  answerStrategy: AnswerStrategy;
  fullContextAvailable: boolean;
  pending: boolean;
  inputRef?: RefObject<HTMLTextAreaElement>;
  onQuestionChange: (question: string) => void;
  onFacetsChange: (facets: AnswerFacets) => void;
  onAnswerStrategyChange: (strategy: AnswerStrategy) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const settingsDisclosureRef = useRef<HTMLDetailsElement>(null);
  const questionId = `archivist-question-${location}`;
  const lensId = `archivist-lens-${location}`;
  const voiceId = `archivist-voice-${location}`;
  const worldviewId = `archivist-worldview-${location}`;
  const facetDescriptionId = `archivist-facet-description-${location}`;
  const scopeDescriptionId = `archivist-scope-description-${location}`;
  const scopeName = `archivist-evidence-scope-${location}`;
  const groundingId = `question-grounding-note-${location}`;
  const evidenceScopeSettings = (
    <fieldset className="chat-evidence-scope" aria-describedby={scopeDescriptionId}>
      <legend>Evidence scope</legend>
      <p id={scopeDescriptionId}>
        Which part of the manuscript Archivist reads before answering. This does not
        change the lens, voice, or worldview.
      </p>
      <div className="chat-evidence-scope-options">
        <label>
          <input
            type="radio"
            name={scopeName}
            value="rag"
            checked={answerStrategy === "rag"}
            disabled={pending}
            onChange={() => onAnswerStrategyChange("rag")}
          />
          <span>
            <strong>Retrieved passages</strong>
            <small>Fast and inexpensive. Retrieves the most relevant passages.</small>
          </span>
        </label>
        <label
          title={fullContextAvailable
            ? undefined
            : "Not enabled on this deployment"}
        >
          <input
            type="radio"
            name={scopeName}
            value="full_context"
            checked={answerStrategy === "full_context"}
            disabled={pending || !fullContextAvailable}
            onChange={() => onAnswerStrategyChange("full_context")}
          />
          <span>
            <strong>Full book</strong>
            <small>
              Experimental. Slower and more expensive. Gives the model the complete
              searchable manuscript instead of a retrieved excerpt.
            </small>
          </span>
        </label>
      </div>
    </fieldset>
  );
  const answerSettings = (
    <fieldset className="chat-answer-settings" aria-describedby={facetDescriptionId}>
      <legend>Interpretive settings</legend>
      <div className="chat-answer-settings-heading">
        <p id={facetDescriptionId}>
          A non-default lens or worldview shapes the opening and conclusion around the cited
          manuscript answer; voice changes expression.
        </p>
        <span>{answerFacetSummary(facets)}</span>
      </div>
      <div className="chat-facet-grid">
        <FacetSelect
          id={lensId}
          label="Historiographical lens"
          value={facets.historiographicalLens}
          options={LENS_OPTIONS}
          disabled={pending}
          onChange={(historiographicalLens) => onFacetsChange({
            ...facets,
            historiographicalLens
          })}
        />
        <FacetSelect
          id={voiceId}
          label="Voice"
          value={facets.voice}
          options={VOICE_OPTIONS}
          disabled={pending}
          onChange={(voice) => onFacetsChange({ ...facets, voice })}
        />
        <FacetSelect
          id={worldviewId}
          label="Worldview"
          value={facets.worldview}
          options={WORLDVIEW_OPTIONS}
          disabled={pending}
          onChange={(worldview) => onFacetsChange({ ...facets, worldview })}
        />
      </div>
    </fieldset>
  );

  return (
    <form
      className={`chat-composer ${location === "thread" ? "is-docked" : "is-landing"}`}
      aria-label={`Ask a question about ${project.name}`}
      aria-busy={pending}
      onSubmit={(event) => {
        if (settingsDisclosureRef.current) settingsDisclosureRef.current.open = false;
        onSubmit(event);
      }}
    >
      <label className="chat-question-field" htmlFor={questionId}>
        <span>{location === "landing" ? "Begin the conversation" : "Your next question"}</span>
        <textarea
          ref={inputRef}
          id={questionId}
          rows={location === "landing" ? 2 : 1}
          required
          maxLength={4_000}
          aria-describedby={groundingId}
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (!pending && question.trim()) event.currentTarget.form?.requestSubmit();
            }
          }}
          placeholder={location === "landing"
            ? "What would you like to know about Cradle of the Empire?"
            : "Ask a follow-up question..."}
        />
      </label>

      <div className="chat-composer-options">
        <details className="chat-answer-settings-disclosure" ref={settingsDisclosureRef}>
          <summary aria-label={`Answer style: ${answerFacetSummary(facets)}`}>
            <SlidersHorizontal size={16} aria-hidden="true" />
            <span>
              <small>Answer style</small>
              <strong>{compactAnswerFacetSummary(facets)}</strong>
            </span>
            <ChevronDown size={14} aria-hidden="true" />
          </summary>
          <div className="chat-answer-settings-panel">
            {evidenceScopeSettings}
            {answerSettings}
          </div>
        </details>

        <div className="chat-composer-submit">
          <span id={groundingId}>
            <i aria-hidden="true" />
            {pending
              ? answerStrategy === "full_context"
                ? "Reading the full manuscript — this takes noticeably longer"
                : "You can draft the next question while Archivist works"
              : `${project.stats.searchable_chunks.toLocaleString()} searchable manuscript passages`}
          </span>
          <button type="submit" disabled={pending || !question.trim()}>
            {pending ? <Loader2 size={17} className="spin" /> : <Send size={16} />}
            <span>{pending ? "Reading" : location === "landing" ? "Ask" : "Send"}</span>
          </button>
        </div>
      </div>
      <small className="composer-key-hint">Enter to send · Shift + Enter for a new line</small>
    </form>
  );
}

function FacetSelect<T extends string>({
  id,
  label,
  value,
  options,
  disabled,
  onChange
}: {
  id: string;
  label: string;
  value: T;
  options: ReadonlyArray<FacetOption<T>>;
  disabled: boolean;
  onChange: (value: T) => void;
}) {
  const selected = facetOption(options, value);
  return (
    <div className="chat-facet-control">
      <label htmlFor={id}>{label}</label>
      <div>
        <select
          id={id}
          value={value}
          disabled={disabled}
          title={selected.description}
          onChange={(event) => onChange(event.target.value as T)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <ChevronDown size={14} aria-hidden="true" />
      </div>
    </div>
  );
}

function ConversationTurn({
  turn,
  turnNumber,
  copied,
  onCopy,
  onRetry,
  onApprove,
  publicDemo
}: {
  turn: ChatTurn;
  turnNumber: number;
  copied: boolean;
  onCopy: () => void;
  onRetry: () => void;
  onApprove: () => void;
  publicDemo: boolean;
}) {
  const headingId = `turn-${turn.id}-question`;
  const sourceScopeId = `turn-${turn.id}-sources`;
  const sourceCount = publicDemo
    ? turn.sources.length
    : turn.displayGroups.reduce(
        (count, group) => count + group.source_numbers.length,
        0
      );
  const facetSummary = answerFacetSummary(turn.facets);

  return (
    <article className={`conversation-turn is-${turn.status}`} id={`turn-${turn.id}`} aria-labelledby={headingId}>
      <div className="user-turn">
        <span>You</span>
        <h2 id={headingId}>{turn.question}</h2>
      </div>

      <div className="archivist-turn">
        <header className="archivist-turn-header">
          <div className="archivist-identity">
            <span><Library size={15} /></span>
            <div>
              <strong>Archivist</strong>
              <small className="sr-only">Turn {turnNumber}</small>
              {facetSummary !== "Neutral baseline" ? (
                <span className="turn-facet-summary">
                  <span><i>Style</i>{facetSummary}</span>
                </span>
              ) : null}
            </div>
          </div>
        </header>

        {turn.status === "pending" ? (
          <div className="archivist-thinking">
            <ProcessStatus messages={QUESTION_STEPS} />
            <p>{turnNumber > 1 ? "Following the thread, then returning to the manuscript." : "Finding the passages that best answer your question."}</p>
          </div>
        ) : null}

        {turn.status === "error" ? (
          <div className="turn-error" role="alert">
            <AlertCircle size={18} />
            <div>
              <strong>
                {turn.budgetBlocked
                  ? "The local monthly cost limit stopped this request."
                  : turn.answerStatus === "generation_contract_failed"
                    ? "Archivist rejected an unverified response."
                    : "Archivist could not complete this answer."}
              </strong>
              <p>{turn.error}</p>
              {!publicDemo && (turn.validationErrorCode || turn.turnCostUsd !== undefined) ? (
                <details className="turn-error-details">
                  <summary>Technical details</summary>
                  {turn.validationErrorCode ? (
                    <span>Validation code: <code>{turn.validationErrorCode}</code></span>
                  ) : null}
                  {turn.stageTimingsMs?.total !== undefined ? (
                    <span>Total time: {(turn.stageTimingsMs.total / 1000).toFixed(1)} seconds</span>
                  ) : null}
                  {turn.turnCostUsd !== undefined ? (
                    <span>Estimated API cost: {formatTurnCost(turn.turnCostUsd)}</span>
                  ) : null}
                </details>
              ) : null}
            </div>
            {turn.budgetBlocked && !publicDemo ? (
              <button type="button" onClick={onApprove}>
                <CircleDollarSign size={15} />
                Approve one request
              </button>
            ) : (
              <button type="button" onClick={onRetry}>
                <RotateCcw size={15} />
                {turn.answerStatus === "generation_contract_failed" ? "Retry request" : "Try again"}
              </button>
            )}
          </div>
        ) : null}

        {turn.status === "complete" ? (
          <div className="archivist-response">
            <span className="sr-only" role="status">Archivist's answer is ready.</span>
            <div className="assistant-paper">
              <OutputBlock
                title="Archivist's answer"
                body={turn.answer}
                empty=""
                sources={turn.sources}
                sourceScopeId={sourceScopeId}
              />
            </div>
            <div className="archivist-response-footer">
              {sourceCount ? (
                <details className="turn-sources-disclosure">
                  <summary>
                    <span>
                      <BookOpen size={15} aria-hidden="true" />
                      <strong>Sources</strong>
                      <small>{sourceCount} {sourceCount === 1 ? "passage" : "passages"}</small>
                    </span>
                    <ChevronDown size={15} aria-hidden="true" />
                  </summary>
                  {publicDemo ? (
                    <PublicSources
                      sources={turn.sources.filter(isPublicSource)}
                      sourceScopeId={sourceScopeId}
                    />
                  ) : (
                    <DisplayGroups
                      title="Manuscript sources"
                      groups={turn.displayGroups}
                      sourceScopeId={sourceScopeId}
                    />
                  )}
                </details>
              ) : null}
              <div className="turn-response-actions">
                {turn.answerStrategy === "full_context" ? (
                  <span className="turn-strategy-chip">Full book</span>
                ) : null}
                {turn.turnCostUsd !== undefined ? (
                  <span className="turn-cost-chip">Est. {formatTurnCost(turn.turnCostUsd)}</span>
                ) : null}
                <button
                  type="button"
                  className="copy-answer-button"
                  aria-label={copied ? "Answer copied" : "Copy answer"}
                  title={copied ? "Answer copied" : "Copy answer"}
                  onClick={onCopy}
                >
                  {copied
                    ? <CheckCircle2 size={15} aria-hidden="true" />
                    : <Copy size={15} aria-hidden="true" />}
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </article>
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

function OutputBlock({
  title,
  body,
  empty,
  sources = [],
  sourceScopeId
}: {
  title: string;
  body: string;
  empty: string;
  sources?: SourceReference[];
  sourceScopeId?: string;
}) {
  const paragraphs = body ? body.split(/\n{2,}/) : [];
  return (
    <section className="output-block">
      <div className="panel-title">
        <h2>{title}</h2>
        <BookOpen size={17} />
      </div>
      {body ? (
        <div className="answer-copy">
          {paragraphs.map((paragraph, index) => (
            <p key={index}>
              <CitationText body={paragraph} sources={sources} sourceScopeId={sourceScopeId} />
            </p>
          ))}
        </div>
      ) : <p className="empty-state">{empty}</p>}
    </section>
  );
}

function CitationText({
  body,
  sources,
  sourceScopeId
}: {
  body: string;
  sources: SourceReference[];
  sourceScopeId?: string;
}) {
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

        const resolvedSources = citedSources as SourceReference[];
        const firstSource = resolvedSources[0];
        const excerptText = (
          isPublicSource(firstSource)
            ? firstSource.excerpt ?? firstSource.citation_label
            : firstSource.text
        ).replace(/\s+/g, " ").trim();
        const excerpt = excerptText.slice(0, 220);
        const humanLabels = resolvedSources.map((source) => source.citation_label).join("; ");
        const controlledSourceId = sourceScopeId
          ? scopedSourceAnchor(sourceScopeId, firstSource.source_number)
          : undefined;
        return (
          <button
            key={`${part}-${index}`}
            className="inline-citation"
            type="button"
            aria-label={`Open source: ${humanLabels}`}
            aria-controls={controlledSourceId}
            title={humanLabels}
            onClick={() => openSource(firstSource, sourceScopeId)}
          >
            [{sourceNumbers.join(", ")}]
            <span className="citation-preview" aria-hidden="true">{excerpt}{excerptText.length > 220 ? "…" : ""}</span>
          </button>
        );
      })}
    </>
  );
}

function sourceAnchor(source: SourceChunk) {
  return `source-${source.chunk_ids.join("-").replace(/[^a-z0-9_-]/gi, "-")}`;
}

function scopedSourceAnchor(scopeId: string, sourceNumber: number) {
  return `${scopeId}-source-${sourceNumber}`;
}

function openSource(source: SourceReference, sourceScopeId?: string) {
  const anchor = sourceScopeId
    ? document.getElementById(scopedSourceAnchor(sourceScopeId, source.source_number))
    : document.querySelector<HTMLElement>(`[data-source-numbers~="${source.source_number}"]`)
      ?? (
        isPublicSource(source)
          ? null
          : document.getElementById(sourceAnchor(source))
      );
  const details = anchor instanceof HTMLDetailsElement
    ? anchor
    : anchor?.closest<HTMLDetailsElement>("details");
  let disclosure = details;
  while (disclosure) {
    disclosure.open = true;
    disclosure = disclosure.parentElement?.closest<HTMLDetailsElement>("details") ?? null;
  }
  const summary = details?.querySelector<HTMLElement>("summary");
  summary?.focus({ preventScroll: true });
  const behavior: ScrollBehavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ? "auto"
    : "smooth";
  details?.scrollIntoView({ behavior, block: "center" });
}

function PublicSources({
  sources,
  sourceScopeId
}: {
  sources: PublicSource[];
  sourceScopeId: string;
}) {
  return (
    <section className="sources-block public-sources-block" id={sourceScopeId}>
      <div className="panel-title">
        <h2>Edition references</h2>
        <span>
          Typeset PDF · {sources.length} {sources.length === 1 ? "source" : "sources"}
        </span>
      </div>
      <div className="source-stack">
        {sources.map((source) => (
          <details
            id={scopedSourceAnchor(sourceScopeId, source.source_number)}
            key={source.source_number}
            className="source-card public-source-card"
            data-source-numbers={source.source_number}
          >
            <summary>
              <strong>{source.title}</strong>
              <span>Source {source.source_number} · {source.locator.label}</span>
            </summary>
            <div className="source-card-body">
              <p className="public-edition-label">{source.edition.name}</p>
              {source.excerpt ? (
                <blockquote>{source.excerpt}</blockquote>
              ) : (
                <p className="public-source-location-only">
                  This reference is shown by location without a quoted excerpt.
                </p>
              )}
              <button
                className="copy-reference"
                type="button"
                onClick={() => navigator.clipboard.writeText(source.citation_label)}
              >
                <Copy size={14} />
                Copy edition reference
              </button>
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

function DisplayGroups({
  title,
  groups,
  sourceScopeId
}: {
  title: string;
  groups: DisplayGroup[];
  sourceScopeId?: string;
}) {
  const sourceCount = groups.reduce((count, group) => count + group.source_numbers.length, 0);

  return (
    <section className="sources-block" id={sourceScopeId}>
      <div className="panel-title">
        <h2>{title}</h2>
        <span>{sourceCount} {sourceCount === 1 ? "source" : "sources"}</span>
      </div>
      {groups.length ? (
        <div className="source-stack">
          {groups.map((group, groupIndex) => {
            const sourceNumbers = group.source_numbers.join(" ");
            const sourceLabel = group.source_numbers.map((sourceNumber) => `Source ${sourceNumber}`).join(", ");
            const primarySourceAnchor = sourceScopeId
              ? scopedSourceAnchor(sourceScopeId, group.source_numbers[0])
              : undefined;
            return (
              <details
                id={primarySourceAnchor}
                key={`${sourceNumbers}-${groupIndex}`}
                className="source-card"
                data-source-numbers={sourceNumbers}
              >
                <summary>
                  <strong>{group.citation_labels.join("; ")}</strong>
                  <span>{sourceLabel}</span>
                </summary>
                {sourceScopeId ? group.source_numbers.slice(1).map((sourceNumber) => (
                  <span
                    key={sourceNumber}
                    id={scopedSourceAnchor(sourceScopeId, sourceNumber)}
                    className="sr-only"
                    aria-hidden="true"
                  />
                )) : null}
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
  const isError = notice.type === "error";
  return (
    <div
      className={`notice-banner ${notice.type}`}
      role={isError ? "alert" : "status"}
      aria-live={isError ? "assertive" : "polite"}
    >
      <span className="notice-symbol" aria-hidden="true">
        {isError ? <AlertCircle size={17} /> : <CheckCircle2 size={17} />}
      </span>
      <span>{notice.text}</span>
      <button className="notice-dismiss" type="button" aria-label="Dismiss notification" onClick={onClose}>
        <X size={16} />
      </button>
    </div>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

export default App;
