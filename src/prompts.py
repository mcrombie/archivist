from perspectives import AnswerPerspective, build_perspective_prompt_block
from retrieval import build_comparison_context, build_context


ANSWER_PROMPT_TEMPLATE = """You are a historian specializing in the development of the American imperial system through Virginia.

Answer the user's question using only the provided sources.

Cite sources inline after specific claims using [Source X].
Do not group multiple sources only at the end of a paragraph.
Each important factual claim should have its own citation.
If a sentence contains multiple distinct claims, cite each claim separately.
If multiple sources support the same claim, cite them together like [Source 2, Source 3].

Do not place citations only at the end of bullets or paragraphs. Place them immediately after the sentence or clause they support.

Be precise, avoid vague generalizations, and do not invent information.

If the sources do not contain enough information, say so.

Answer in 1–3 short paragraphs or structured bullet points when appropriate.

Question:
{question}

Sources:
{context}
"""

INDEX_PROMPT_TEMPLATE_CLI = """You are helping build a back-of-the-book index for a historical manuscript.

Using only the provided sources, produce a candidate index entry for the term below.

Term:
{term}

Instructions:
- Write a 2-4 sentence summary of how this term is used in the manuscript.
- Then list the strongest candidate locations.
- Then suggest 0-5 possible subentries if they are clearly supported by the sources.
- Be cautious: if the term is only mentioned briefly or weakly, say so.
- Do not invent page numbers.
- Use source numbers when making claims, like [Source 2].

Format exactly like this:

Index term: <term>

Summary:
<summary>

Key locations:
- [Source X] <chapter / chunk / brief note>
- [Source X] <chapter / chunk / brief note>

Suggested subentries:
- <subentry>
- <subentry>

Sources:
{context}
"""

INDEX_PROMPT_TEMPLATE_WEB = """You are helping build a back-of-the-book index for a historical manuscript.

Using only the provided manuscript sources, produce a candidate index entry for the term below.

Term:
{term}

Instructions:
- Write a 2-4 sentence summary of how this term is used in the manuscript.
- Then list the strongest candidate locations.
- Then suggest 0-5 possible subentries if they are clearly supported by the sources.
- Be cautious: if the term is only mentioned briefly or weakly, say so.
- Do not invent page numbers.
- Use [Source N] when making claims.
- If existing index context is supplied, use it only as a comparison reference. Do not copy it blindly.
- Do not cite the existing index context.

Format exactly like this:

Index term: <term>

Summary:
<summary>

Key locations:
- [Source N] <brief note>

Suggested subentries:
- <subentry>

Existing index context:
{existing_context}

Manuscript sources:
{context}
"""


def build_answer_prompt(question: str, final_chunks: list[dict]) -> str:
    return ANSWER_PROMPT_TEMPLATE.format(
        question=question,
        context=build_context(final_chunks),
    )


def build_perspective_answer_prompt(
    question: str,
    final_chunks: list[dict],
    perspective: AnswerPerspective | str,
) -> str:
    prompt = build_answer_prompt(question, final_chunks)
    perspective_block = build_perspective_prompt_block(perspective)
    if not perspective_block:
        return prompt

    question_marker = "\nQuestion:\n"
    if ANSWER_PROMPT_TEMPLATE.count(question_marker) != 1:
        raise RuntimeError("The answer prompt must contain exactly one Question section.")
    return prompt.replace(
        question_marker,
        f"\n{perspective_block}\n\nQuestion:\n",
        1,
    )


def build_index_prompt_cli(term: str, final_chunks: list[dict]) -> str:
    return INDEX_PROMPT_TEMPLATE_CLI.format(
        term=term,
        context=build_context(final_chunks),
    )


def build_index_prompt_web(
    term: str,
    final_chunks: list[dict],
    existing_index_chunks: list[dict],
) -> str:
    existing_context = (
        build_comparison_context(existing_index_chunks)
        if existing_index_chunks
        else "No existing index context supplied."
    )
    return INDEX_PROMPT_TEMPLATE_WEB.format(
        term=term,
        existing_context=existing_context,
        context=build_context(final_chunks),
    )
