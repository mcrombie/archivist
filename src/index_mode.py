from costs import tracked_responses_create
from model_config import GENERATOR_SETTINGS
from prompts import build_index_prompt_cli
from retrieval import default_openai_client, finalize_index_context, retrieve


def generate_index_entry(term: str, final_chunks: list[dict]) -> str:
    prompt = build_index_prompt_cli(term, final_chunks)

    response = tracked_responses_create(
        default_openai_client(),
        operation="index_generation",
        input=prompt,
        **GENERATOR_SETTINGS.responses_create_kwargs(),
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
