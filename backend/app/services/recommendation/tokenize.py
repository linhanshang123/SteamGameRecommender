STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "but",
    "for",
    "from",
    "game",
    "games",
    "i",
    "if",
    "in",
    "it",
    "like",
    "of",
    "or",
    "something",
    "that",
    "the",
    "to",
    "want",
    "with",
}


def tokenize(text: str) -> list[str]:
    normalized = "".join(char if char.isalnum() or char in {" ", "-"} else " " for char in text.lower())
    return [
        token
        for token in (part.strip() for part in normalized.split())
        if len(token) > 1 and token not in STOP_WORDS
    ]


def overlap_score(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0

    a_set = set(a)
    b_set = set(b)
    shared = sum(1 for token in a_set if token in b_set)
    return shared / max(len(a_set), len(b_set))
