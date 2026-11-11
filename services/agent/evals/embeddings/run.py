"""
Measures whether FastEmbed similarity agrees with the user's good/bad labels:
`uv run python -m evals.embeddings.run`. Takes the account with the most
labels, embeds each labeled job and checks, job by job, whether its nearest
labeled neighbors carry the same label. Also reports model load and embedding
times. Runs locally with no Claude calls. Point it at the hosted project by
setting SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY for that project.
"""

import time
from collections import Counter

import numpy as np

from app.config import get_settings
from app.db import service_db
from app.embeddings import FastEmbedEmbeddings, job_text
from evals.labels.run import auc

# Model name, input limit in tokens, prefix the model expects on each text.
MODELS = (
    ("BAAI/bge-small-en-v1.5", 512, ""),
    ("nomic-ai/nomic-embed-text-v1.5-Q", 8192, "clustering: "),
)
NEIGHBORS = 5
CHARS_PER_TOKEN = 4


def evaluate(labels: list[str], vectors: np.ndarray) -> tuple[float, float]:
    """Leave-one-out: each job's share of good among its nearest labeled neighbors; returns accuracy and AUC."""
    similarity = vectors @ vectors.T
    np.fill_diagonal(similarity, -np.inf)
    good_share: list[tuple[str, float]] = []
    correct = 0
    for i, label in enumerate(labels):
        nearest = np.argsort(similarity[i])[::-1][:NEIGHBORS]
        share = sum(labels[j] == "good" for j in nearest) / NEIGHBORS
        good_share.append((label, share))
        correct += (share > 0.5) == (label == "good")
    return correct / len(labels), auc(good_share)


def main() -> None:
    db = service_db(get_settings())
    labeled = db.select("applications", {"select": "user_id", "fit_label": "not.is.null"})
    counts = Counter(row["user_id"] for row in labeled)
    if not counts:
        print("No account has labeled jobs.")
        return
    user_id = counts.most_common(1)[0][0]
    rows = db.select(
        "applications",
        {"select": "fit_label,posting:postings(title,company,location,description)", "user_id": f"eq.{user_id}", "fit_label": "not.is.null"},
    )
    labels = [row["fit_label"] for row in rows]
    texts = [job_text(**row["posting"]) for row in rows]
    tally = Counter(labels)
    if min(tally["good"], tally["bad"]) <= NEIGHBORS:
        print(f"Need more than {NEIGHBORS} jobs per label; have {tally['good']} good, {tally['bad']} bad.")
        return
    empty = sum(not row["posting"]["description"] for row in rows)
    print(f"{len(rows)} labeled jobs: {tally['good']} good, {tally['bad']} bad, {empty} without a description")
    print(f"Always guessing the larger label is right {max(tally.values()) / len(rows):.0%} of the time; AUC by chance is 0.50")

    for name, max_tokens, prefix in MODELS:
        start = time.perf_counter()
        model = FastEmbedEmbeddings(name, max_tokens, prefix)
        loaded = time.perf_counter() - start
        start = time.perf_counter()
        vectors = np.array(model.embed_documents(texts), dtype=np.float32)
        embedded = time.perf_counter() - start
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        accuracy, score_auc = evaluate(labels, vectors)
        cut = sum(len(text) / CHARS_PER_TOKEN > max_tokens for text in texts)
        print(f"\n{name} ({vectors.shape[1]} dimensions, reads {max_tokens} tokens)")
        print(f"  {NEIGHBORS} nearest neighbors agree with the label: {accuracy:.0%}   AUC {score_auc:.2f}")
        print(f"  load {loaded:.1f} s (includes a first download), embed {embedded / len(texts) * 1000:.0f} ms per job")
        print(f"  about {cut} of {len(texts)} jobs are longer than the model reads")


if __name__ == "__main__":
    main()
