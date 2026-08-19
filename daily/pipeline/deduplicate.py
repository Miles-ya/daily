from daily.models import Document


def deduplicate(documents: list[Document]) -> list[Document]:
    by_url: dict[str, Document] = {}
    hashes: set[str] = set()
    for document in documents:
        if document.canonical_url in by_url or document.content_hash in hashes:
            continue
        by_url[document.canonical_url] = document
        hashes.add(document.content_hash)
    return list(by_url.values())
