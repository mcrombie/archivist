import os

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

from retrieval import retrieve, finalize_index_context, build_context

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_index_entry(term: str, final_chunks: list[dict]) -> str:
    context = build_context(final_chunks)

    prompt = f"""You are helping build a back-of-the-book index for a historical manuscript.

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

    response = client.responses.create(
        model="gpt-5",
        input=prompt
    )

    return response.output_text


def main() -> None:
    while True:
        term = input("\nEnter index term (or 'exit'): ").strip()

        if term.lower() == "exit":
            break

        results = retrieve(term)
        final_chunks = finalize_index_context(term, results)
        output = generate_index_entry(term, final_chunks)

        print("\nCandidate index entry:\n")
        print(output)

        print("\nSources shown to model:\n")
        for i, chunk in enumerate(final_chunks, start=1):
            print(f"Source {i}")
            print(f"  Chapter: {chunk.get('chapter_title', 'N/A')}")
            print(f"  Chunk ID: {chunk.get('chunk_id', 'N/A')}")
            print(f"  Paragraphs: {chunk.get('paragraph_start', '?')}–{chunk.get('paragraph_end', '?')}")
            print("-" * 60)


if __name__ == "__main__":
    main()