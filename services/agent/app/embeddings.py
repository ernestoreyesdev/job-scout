from functools import cache

from fastembed import TextEmbedding
from langchain_core.embeddings import Embeddings

MODEL = "BAAI/bge-small-en-v1.5"
MAX_TOKENS = 512


class FastEmbedEmbeddings(Embeddings):
    """LangChain embeddings computed in-process by a FastEmbed model; `prefix` is prepended to every text."""

    def __init__(self, model_name: str, max_length: int, prefix: str = ""):
        self.model = TextEmbedding(model_name=model_name, max_length=max_length)
        self.prefix = prefix

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self.model.embed([self.prefix + text for text in texts])]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def job_text(title: str, company: str, location: str | None, description: str) -> str:
    """The text a job is embedded from."""
    return f"{title} at {company}\n{location or ''}\n{description}"


@cache
def default_model() -> FastEmbedEmbeddings:
    """Loaded once per process; the first load downloads the model."""
    return FastEmbedEmbeddings(MODEL, MAX_TOKENS)


def embed_jobs(texts: list[str]) -> list[list[float]]:
    return default_model().embed_documents(texts)
