from typing import Any

from app.agents.schemas import Usage
from app.agents.tool_loop.prompts import SEARCH_SYSTEM
from app.agents.tool_loop.tools import FALLBACK_BETAS, TOOLS, SearchTools, ToolError

MAX_TURNS = 40


class AgentError(Exception):
    pass


def run_search_agent(client: Any, model: str, tools: SearchTools, request: str, usage: Usage) -> str:
    """Tool-use loop: runs tools until the model stops asking for them, then returns its final text."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": request}]

    for _ in range(MAX_TURNS):
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=FALLBACK_BETAS,
            fallbacks="default",
            output_config={"effort": "low"},
            system=SEARCH_SYSTEM,
            tools=TOOLS,
            messages=messages,
        )
        usage.add(response.usage)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            raise AgentError("The model declined this request.")
        if response.stop_reason != "tool_use":
            return "".join(block.text for block in response.content if block.type == "text")

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = {"type": "tool_result", "tool_use_id": block.id, "content": tools.run(block.name, block.input)}
            except ToolError as error:
                result = {"type": "tool_result", "tool_use_id": block.id, "content": str(error), "is_error": True}
            tool_results.append(result)

        messages.append({"role": "user", "content": tool_results})

    raise AgentError(f"Stopped after {MAX_TURNS} turns without finishing.")
