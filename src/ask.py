import os

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

from retrieval import retrieve, finalize_context_chunks, build_context

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def answer_question(question: str, n_results: int = 5):
    results = retrieve(question, n_results=n_results)
    final_chunks = finalize_context_chunks(results)
    context = build_context(final_chunks)

    prompt = f"""You are a historian specializing in the development of the American imperial system through Virginia.

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

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    return response.output_text, final_chunks


def main() -> None:
    while True:
        question = input("\nAsk a question (or 'exit'): ").strip()

        if question.lower() == "exit":
            break

        answer, final_chunks = answer_question(question)

        print("\nAnswer:\n")
        print(answer)

        print("\nSources shown to model:\n")
        for i, chunk in enumerate(final_chunks, start=1):
            print(f"Source {i}")
            print(f"  Document: {chunk.get('document', 'N/A')}")
            print(f"  Chapter: {chunk.get('chapter_title', 'N/A')}")
            print(f"  Chunk ID: {chunk.get('chunk_id', 'N/A')}")
            print(f"  Paragraphs: {chunk.get('paragraph_start', '?')}–{chunk.get('paragraph_end', '?')}")
            print("-" * 60)


if __name__ == "__main__":
    main()