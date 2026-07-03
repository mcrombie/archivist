cd ..# Archivist

A domain-aware retrieval-augmented generation (RAG) system for historical research and manuscript analysis.

Archivist ingests a large historical manuscript, builds a semantic search index, and provides two primary modes:

- **Answer Mode**: grounded, source-cited responses to historical questions
- **Index Mode**: assists in building a back-of-the-book index by identifying key passages and themes

---

## Overview

Archivist was built to explore how AI can assist with:

- navigating long-form historical writing
- synthesizing arguments across chapters
- identifying key references for indexing and editing

The system is designed around a single manuscript corpus and emphasizes:

- source transparency
- structured retrieval
- reproducible results

---

## Features

### 1. Answer Mode

Ask natural language questions about the manuscript.

Example:

What role did Jamestown play as a corporate experiment?


Archivist will:
- retrieve relevant passages
- construct a grounded answer
- cite sources inline (`[Source X]`)
- display the exact chunks used

---

### 2. Index Assistant Mode

Generate candidate index entries for a term or concept.

Example:

Virginia Company


Archivist will:
- locate relevant passages (exact + semantic retrieval)
- summarize how the term is used
- suggest key locations
- propose subentries when appropriate

---

### 3. Hybrid Retrieval Strategy

Archivist uses multiple retrieval techniques:

- semantic search through embeddings
- exact text matching for index terms
- neighbor chunk expansion for context continuity

---

### 4. Source Transparency

All answers are grounded in explicit source chunks:

- chapter
- paragraph range
- chunk ID

This allows full traceability of generated outputs.

---

## Architecture

Manuscript (Markdown)
↓
Chunking (custom heuristics)
↓
Embeddings (OpenAI)
↓
ChromaDB (vector store)
↓
Retrieval Layer
├── semantic search
├── exact match (index mode)
└── neighbor expansion
↓
Context Finalization
↓
LLM Generation (OpenAI)

---

## Project Structure

src/
corpus.py # chunk loading and structure
retrieval.py # retrieval + context logic
filters.py # document filtering rules
embed.py # embedding pipeline
ask.py # answer mode
index_mode.py # index assistant mode
query.py # basic retrieval testing

output/
chunks.json # processed manuscript chunks

chroma_db/

vector database (ignored in git)

manuscript/

raw manuscript (ignored in git)

---

## Setup


### 1. Install dependencies

pip install openai chromadb python-dotenv


### 2. Add API key

Create a `.env` file in the project root:

OPENAI_API_KEY=your_api_key_here


### 3. Build embeddings

python src/embed.py


### 4. Run Answer Mode

python src/ask.py


### 5. Run Index Mode

python src/index_mode.py


---

## Design Decisions

### Inline Footnotes

Footnotes are embedded directly in text chunks to preserve context during retrieval.

### Chunking Strategy

Chunks are based on paragraph groupings with heuristics to:
- preserve rhetorical flow
- keep quotes attached to analysis
- allow slight overlap across chunks

### Neighbor Expansion

Adjacent chunks are included during retrieval to:
- prevent context fragmentation
- improve answer coherence

### Filtering

Structural documents (e.g., bibliography, table of contents) are excluded from retrieval to avoid noise.

---

## Limitations

- Broad thematic questions may overweight a single section of the manuscript
- No page-number mapping (pending final manuscript formatting)
- CLI-only interface (no UI yet)
- Retrieval tuning is heuristic, not learned

---

## Future Improvements

- Page-level citation mapping
- Query-type-aware retrieval (broad vs. focused questions)
- Improved thematic aggregation across chapters
- UI for browsing results
- Index export tooling

---

## Why This Project

Archivist demonstrates:

- applied use of RAG systems on real-world long-form text
- handling of historical and narrative data (not just structured documents)
- tradeoffs between semantic retrieval and exact matching
- building domain-specific AI tools beyond generic chat interfaces

---

## Author

Michael Crombie  
B.S. Computer Science & History, William & Mary

---

## License

MIT (or choose your preferred license)