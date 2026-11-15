from types import SimpleNamespace
from typing import Any, cast

from app.config import Settings


class FakeParse:
    """A Claude client's messages whose parse records each call and returns `output`; None reads as a refusal."""

    def __init__(self, output: Any, input_tokens: int = 0, output_tokens: int = 0):
        self.output = output
        self.usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        stop_reason = "end_turn" if self.output is not None else "refusal"
        return SimpleNamespace(parsed_output=self.output, stop_reason=stop_reason, usage=self.usage)


def claude(messages: Any) -> SimpleNamespace:
    """A Claude client whose beta.messages are `messages`."""
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


def fake_settings(**fields: Any) -> Settings:
    return cast(Settings, SimpleNamespace(**fields))
