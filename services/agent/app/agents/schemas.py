from pydantic import BaseModel, Field, field_validator

from app.sources.base import WorkplaceType


class FitScore(BaseModel):
    score: int = Field(ge=0, le=100, description="0-100 fit of the resume for this job.")
    summary: str = Field(description="Two or three sentences explaining the score.")
    strengths: list[str] = Field(description="Resume evidence that matches the job's requirements.")
    gaps: list[str] = Field(description="Job requirements the resume does not show.")


class SearchRule(BaseModel):
    """What a search looks for. Without a company it covers every company in the directory."""

    keywords: list[str] = Field(min_length=1)
    company: str | None = Field(default=None, max_length=100)
    workplace_types: list[WorkplaceType] = []
    location: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=10, ge=1, le=25)

    @field_validator("keywords")
    @classmethod
    def keywords_not_blank(cls, keywords: list[str]) -> list[str]:
        cleaned = [keyword.strip() for keyword in keywords if keyword.strip()]
        if not cleaned:
            raise ValueError("Enter at least one keyword.")
        return cleaned

    @field_validator("company", "location")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class AnthropicKeyRequest(BaseModel):
    api_key: str = Field(min_length=20)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    web_search_requests: int = 0

    def add(self, usage: object) -> None:
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.cache_read_input_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.cache_creation_input_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.web_search_requests += getattr(getattr(usage, "server_tool_use", None), "web_search_requests", 0) or 0
