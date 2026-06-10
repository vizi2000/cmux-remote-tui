"""Domain protocols (ports) for dependency inversion.

CmuxClient and LlmProvider are the core ports.
Infrastructure provides adapters.
"""

from __future__ import annotations
from typing import Protocol, List, Optional, Any
from .models import CmuxTree, SurfaceRef, ScreenSnapshot, SynthesisContext, SynthesisResult


class CmuxClient(Protocol):
    """Port for interacting with remote cmux instance.

    Mirrors cmux CLI capabilities + batch for efficiency.
    Implementations: SshCmuxClient (persistent), perhaps LocalDirect in future.
    """

    def get_tree(self) -> CmuxTree:
        """Return full hierarchical tree."""
        ...

    def read_screen(self, ref: SurfaceRef, lines: int = 200, scrollback: bool = False) -> ScreenSnapshot:
        ...

    def send_keys(self, ref: SurfaceRef, events: List[Any]) -> ScreenSnapshot:
        """Send batch of events (text or key), return updated screen."""
        ...

    def execute(self, argv: List[str]) -> dict:
        """Raw cmux command, return result dict."""
        ...

    def read_many(self, refs: List[SurfaceRef], lines: int = 200) -> dict[SurfaceRef, ScreenSnapshot]:
        """Batch read for LLM synthesis efficiency."""
        ...

    def start(self) -> bool:
        """Connect if needed."""
        ...

    def stop(self) -> None:
        ...

    @property
    def connected(self) -> bool:
        ...

    @property
    def last_err(self) -> str:
        ...


class LlmProvider(Protocol):
    """Port for LLM synthesis.

    Supports user's providers: local CLIs (grok/claude/codex), OpenRouter, OpenAI-compatible.
    """

    def synthesize(self, prompt: str, context: SynthesisContext, temperature: float = 0.2, max_tokens: int = 2000) -> SynthesisResult:
        ...

    @property
    def provider_name(self) -> str:
        ...

    @property
    def model(self) -> str:
        ...
