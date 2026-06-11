"""Infrastructure LLM adapters.

Implements LlmProvider port for local CLIs and OpenAI-compatible (incl. OpenRouter).
"""

from __future__ import annotations
import time
from typing import Any

from ..domain.protocols import LlmProvider
from ..domain.models import SynthesisContext, SynthesisResult, PerSurfaceState, SurfaceRef
from ..llm import get_llm, LLMClient  # the existing factory


class OpenAiLlmProvider(LlmProvider):
    """Adapter for OpenRouter / OpenAI-compatible (and local if exposed via OpenAI API)."""

    def __init__(self, provider: str = "openai-compatible", **kwargs: Any):
        self._client: LLMClient = get_llm(provider, **kwargs)

    @property
    def provider_name(self) -> str:
        return self._client.config.provider

    @property
    def model(self) -> str:
        return self._client.config.model

    def synthesize(self, prompt: str, context: SynthesisContext, temperature: float = 0.2, max_tokens: int = 2000) -> SynthesisResult:
        raw = self._client.synthesize(prompt, temperature, max_tokens)
        # Parse simple structured output from markdown-ish response for v0.2.
        # In full version use Pydantic + instructor or json mode.
        per_surface: list[PerSurfaceState] = []
        focus_list: list[str] = []
        lines = raw.splitlines()
        current_ref = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("[") and "]" in line:
                current_ref = line.split("]")[0].strip("[]")
            if "state:" in line.lower() or "priority" in line.lower():
                # naive parse
                state = "working"
                prio = 3
                if "stuck" in line.lower():
                    state = "stuck"
                if "done" in line.lower():
                    state = "done"
                if "error" in line.lower():
                    state = "error"
                for p in range(1, 6):
                    if str(p) in line:
                        prio = p
                if current_ref:
                    per_surface.append(PerSurfaceState(
                        ref=SurfaceRef(current_ref),
                        agent_type="unknown",
                        current_task="see screen",
                        state=state,  # type: ignore
                        last_output_summary=line,
                        priority=prio
                    ))
            if line.startswith(("1.", "2.", "3.", "4.", "5.")) or "prioritized" in line.lower():
                focus_list.append(line)
        return SynthesisResult(
            per_surface=per_surface or [PerSurfaceState(SurfaceRef("demo"), "demo", "demo", "working", raw[:100], 3)],
            global_focus_list=focus_list or ["See raw output"],
            raw_text=raw,
            timestamp=time.time(),
        )


class LocalCliLlmProvider(LlmProvider):
    """Adapter for local grok/claude/codex CLIs."""

    def __init__(self, provider: str = "local-claude", **kwargs: Any):
        self._client: LLMClient = get_llm(provider, **kwargs)

    @property
    def provider_name(self) -> str:
        return self._client.config.provider

    @property
    def model(self) -> str:
        return self._client.config.model

    def synthesize(self, prompt: str, context: SynthesisContext, temperature: float = 0.2, max_tokens: int = 2000) -> SynthesisResult:
        raw = self._client.synthesize(prompt, temperature, max_tokens)
        return SynthesisResult(
            per_surface=[PerSurfaceState(SurfaceRef("local"), "local-cli", "see output", "working", raw[:200], 3)],
            global_focus_list=["Review LLM output in raw"],
            raw_text=raw,
            timestamp=time.time(),
        )


# Factory to pick adapter based on provider string
def make_llm_provider(provider: str = "openai-compatible", **kwargs: Any) -> LlmProvider:
    if provider.startswith("local-"):
        return LocalCliLlmProvider(provider, **kwargs)
    return OpenAiLlmProvider(provider, **kwargs)
