from functools import cache
from pathlib import Path

from langchain_core.embeddings import Embeddings

MODEL = "BAAI/bge-small-en-v1.5"
MAX_TOKENS = 512
MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "bge-small-en-v1.5"


class FastEmbedEmbeddings(Embeddings):
    """LangChain embeddings computed in-process by a FastEmbed model; `prefix` is prepended to every text."""

    def __init__(self, model_name: str, max_length: int, prefix: str = "", path: Path | None = None):
        from fastembed import TextEmbedding

        local = {"specific_model_path": str(path), "local_files_only": True} if path else {}
        self.model = TextEmbedding(model_name=model_name, max_length=max_length, **local)
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
    """Loaded once per process from the model files shipped in MODEL_PATH."""
    return FastEmbedEmbeddings(MODEL, MAX_TOKENS, path=MODEL_PATH)


def embed_jobs(texts: list[str]) -> list[list[float]]:
    return default_model().embed_documents(texts)


def resume_chunks(text: str, max_chars: int = 1500) -> list[str]:
    """The resume split at line breaks into pieces of up to max_chars, each short enough for the model to read whole."""
    chunks: list[str] = []
    current = ""
    for line in (line.strip() for line in text.splitlines()):
        if not line:
            continue
        if current and len(current) + 1 + len(line) > max_chars:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line[:max_chars]
    if current:
        chunks.append(current)
    return chunks
