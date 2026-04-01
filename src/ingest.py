from pathlib import Path
import re

def extract_chapter_title(text, fallback):
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback



def split_into_paragraphs(text):
    lines = text.split("\n")
    paragraphs = []

    for line in lines:
        cleaned = line.strip()

        if not cleaned:
            continue
        if cleaned == "[IMAGE]":
            continue
        if cleaned.startswith("#"):
            continue

        paragraphs.append(cleaned)

    return paragraphs



BASE_DIR = Path(__file__).resolve().parent.parent
manuscript_dir = BASE_DIR / "manuscript"

files = list(manuscript_dir.glob("*.md"))

print("Looking in:", manuscript_dir)
print(f"Found {len(files)} markdown files.\n")

# for file in files:
#     text = file.read_text(encoding="utf-8")
#     chapter_title = extract_chapter_title(text, file.stem)[3:]

#     print(f"--- {file.name} ---")
#     print(f"--- {chapter_title} ---") 
#     print()


# NUMBER OF PARAGRAPHS IN EACH CHAPTER
# for file in files:
#     text = file.read_text(encoding="utf-8")
#     paragraphs = split_into_paragraphs(text)

#     print(f"{file.name}: {len(paragraphs)} paragraphs")




for index, paragraph in enumerate(split_into_paragraphs(files[8].read_text(encoding="utf-8"))):
    print ("PARAGRAPH: " + str(index) + " " + paragraph)