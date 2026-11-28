from typing import Any

from app.telemetry import claude_step

DEFAULT_EFFORT = "low"


def parse(
    client: Any,
    *,
    model: str,
    max_tokens: int,
    step: str,
    system: str,
    content: Any,
    output_format: type,
    error: type[Exception],
    failure: str,
    effort: str = DEFAULT_EFFORT,
) -> Any:
    """
    One structured Claude call, recorded under `step`; raises `error` with
    `failure` when Claude refuses or the reply doesn't parse.
    """
    with claude_step(step):
        response = client.beta.messages.parse(
            model=model,
            max_tokens=max_tokens,
            output_config={"effort": effort},
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=output_format,
        )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise error(f"{failure} failed (stop reason: {response.stop_reason}).")
    return response.parsed_output
