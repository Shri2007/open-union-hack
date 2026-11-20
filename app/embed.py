"""Text embeddings for coalition needs, stored in SingleStore VECTOR columns.

A small local embedding: hashed word and character-trigram features, L2-normalized so SingleStore's
dot product (<*>) is cosine similarity. No API key and no network, so matching never waits on a model.
It only shortlists candidates; TypeSafe still makes the actual same-service judgment.
"""
import hashlib
import math
import re

DIMS = 384

# Different words for the same thing, so "cell plan" and "mobile plan" land near "phone plan".
SYNONYMS = {
    "cell": "phone", "cellphone": "phone", "mobile": "phone", "wireless": "phone", "smartphone": "phone",
    "carrier": "phone", "sim": "phone", "cheaper": "cheap", "lower": "cheap", "discount": "cheap",
    "internet": "broadband", "wifi": "broadband", "isp": "broadband", "electricity": "power",
    "electric": "power", "utility": "power", "auto": "car",
}
STOPWORDS = {"a", "an", "the", "i", "my", "me", "want", "need", "for", "to", "of", "and", "or", "under",
             "below", "less", "than", "per", "month", "monthly", "mo", "pay", "paying", "now", "currently",
             "is", "am", "on", "with", "in", "get", "looking", "cheap", "bill", "price", "plan", "deal"}


def _tokens(text: str) -> list[str]:
    words = [SYNONYMS.get(w, w) for w in re.findall(r"[a-z]+", text.lower())]
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def _bucket(feature: str) -> tuple[int, float]:
    h = hashlib.blake2b(feature.encode(), digest_size=8).digest()
    n = int.from_bytes(h, "big")
    return n % DIMS, (1.0 if (n >> 63) & 1 else -1.0)


def embed(text: str) -> list[float]:
    vec = [0.0] * DIMS
    for w in _tokens(text):
        i, s = _bucket("w:" + w)
        vec[i] += 2.0 * s  # whole words count more than fragments
        padded = f"^{w}$"
        for k in range(len(padded) - 2):
            i, s = _bucket("t:" + padded[k:k + 3])
            vec[i] += 0.5 * s
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def to_sql(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
