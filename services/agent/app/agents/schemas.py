from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.sources.base import WorkplaceType


class FitScore(BaseModel):
    score: int = Field(ge=0, le=100, description="0-100 fit of the resume for this job.")
    summary: str = Field(description="Two or three sentences explaining the score.")
    strengths: list[str] = Field(description="Resume evidence that matches the job's requirements.")
    gaps: list[str] = Field(description="Job requirements the resume does not show.")


class SearchRule(BaseModel):
    """
    What a search looks for. Without a company it covers every company in the
    directory. With web_lookup, a company no board spelling matches is looked
    up with a web search. Exclude drops jobs whose title has any of its words;
    posted_within_days keeps jobs posted in that many days (undated ones pass).
    """

    keywords: list[str] = Field(min_length=1)
    company: str | None = Field(default=None, max_length=100)
    workplace_types: list[WorkplaceType] = []
    location: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=10, ge=1, le=25)
    web_lookup: bool = False
    exclude: list[str] = []
    posted_within_days: Literal[1, 3, 7, 14, 30] | None = None

    @field_validator("keywords")
    @classmethod
    def keywords_not_blank(cls, keywords: list[str]) -> list[str]:
        cleaned = [keyword.strip() for keyword in keywords if keyword.strip()]
        if not cleaned:
            raise ValueError("Enter at least one keyword.")
        return cleaned

    @field_validator("exclude")
    @classmethod
    def drop_blank_exclusions(cls, exclude: list[str]) -> list[str]:
        return [word.strip() for word in exclude if word.strip()]

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


class CompanyName(BaseModel):
    board: str = Field(description="The board value exactly as given, e.g. 'workday/cvshealth.wd1/cvs_health_careers'.")
    name: str = Field(description="The employer's name as people write it.")
    kind: Literal["employer", "staffing", "aggregator"] = Field(
        description=(
            "employer: hires people onto its own payroll to do its work, including consulting, IT services and "
            "agency firms whose own employees serve clients. staffing: recruits people to fill jobs at other "
            "companies (recruitment, contract staffing, talent placement). aggregator: reposts other companies' jobs."
        )
    )


class CompanyNames(BaseModel):
    companies: list[CompanyName]


class Shortlist(BaseModel):
    ids: list[int] = Field(description="Numbers of the best-fitting jobs, best first.")


class CompanyImport(BaseModel):
    """Companies to add to the directory, each a careers page URL or a company name."""

    entries: list[str] = Field(min_length=1, max_length=100)


class HiringJob(BaseModel):
    post: int = Field(description="Number of the post the role comes from.")
    company: str = Field(description="The hiring company's name as people write it.")
    title: str = Field(description="One role's job title, e.g. 'Senior Backend Engineer'.")
    location: str | None = Field(description="Where the role is based, as the post states it, e.g. 'Remote (US)' or 'NYC'.")
    workplace_type: WorkplaceType | None = Field(description="onsite, hybrid or remote when the post says; otherwise null.")


class HiringJobs(BaseModel):
    jobs: list[HiringJob]
