SKIP_FILES = {
    "01_Front Matter.md",
    "02_Table of Contents.md",
    "03_Acknowledgments.md",
    "04_Note on Illustrations.md",
    "32_Bibliography.md",
}

def should_skip_document(doc_name: str) -> bool:
    """
    Returns True if a document should be excluded from retrieval/indexing.
    Uses substring matching to be robust to naming variations.
    """
    name = doc_name.lower()

    for skip in SKIP_FILES:
        if skip.lower() in name:
            return True

    return False
