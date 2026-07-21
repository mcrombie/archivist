from prompts import build_answer_prompt
from retrieval import default_openai_client, finalize_context_chunks, retrieve


def answer_question(question: str, n_results: int = 5):
    results = retrieve(question, n_results=n_results)
    final_chunks = finalize_context_chunks(results)
    prompt = build_answer_prompt(question, final_chunks)

    response = default_openai_client().responses.create(
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
