import re

from openai import AsyncOpenAI

_CODE_BLOCK_RE = re.compile(r"```[\w]*\n(.*?)```", re.DOTALL)


def _has_code_blocks(text: str) -> bool:
    return bool(_CODE_BLOCK_RE.search(text))


def _extract_output_text(response) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str):
        return text.strip()
    return ""


async def apply_guardrails(client: AsyncOpenAI, model: str, text: str, response_language: str) -> str:
    """Rewrite code blocks so the tutoring answer stays non-runnable."""
    if not _has_code_blocks(text):
        return text

    instructions = (
        "Rewrite any runnable code blocks into concise conceptual guidance. "
        "Preserve all non-code text. Replace code with bullets or clearly non-runnable pseudocode. "
        "Do not introduce executable code. "
        f"Write the rewritten answer entirely in {response_language}."
    )

    response = await client.responses.create(
        model=model,
        instructions=instructions,
        input=text,
    )
    rewritten = _extract_output_text(response)
    return rewritten or text
