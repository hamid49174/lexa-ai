"""Controlled trace sampling for synthetic Lexa agent runs.

Runtime traces are useful for replay evals, but unsafe if they capture real
conversation, memory, clipboard, or OS content. This module keeps sampling
explicit, test/synthetic scoped, bounded, and directed only at ignored paths.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.agent_protocol import redacted_metadata, redacted_summary, trace_path_is_safe


def env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AgentTraceSamplingPolicy:
    enabled: bool = False
    sample_rate: float = 0.0
    allowed_sources: set[str] = field(default_factory=lambda: {"synthetic", "test", "eval", "fixture"})
    denied_sources: set[str] = field(default_factory=lambda: {"runtime", "production", "user"})
    max_events_per_run: int = 100
    max_metadata_chars: int = 160
    require_synthetic_context: bool = True
    output_dir: Path = field(default_factory=lambda: Path("evals/results/traces"))
    redact_level: str = "strict"
    seed: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_rate", max(0.0, min(1.0, float(self.sample_rate))))
        object.__setattr__(self, "max_events_per_run", max(0, int(self.max_events_per_run)))
        object.__setattr__(self, "max_metadata_chars", max(32, int(self.max_metadata_chars)))
        object.__setattr__(self, "allowed_sources", {str(source).lower() for source in self.allowed_sources})
        object.__setattr__(self, "denied_sources", {str(source).lower() for source in self.denied_sources})
        object.__setattr__(self, "output_dir", Path(self.output_dir).expanduser())
        # Dedicated RNG so sampling decisions are decoupled from the global
        # random state and reproducible for eval runs when a seed is given.
        object.__setattr__(self, "_rng", random.Random(self.seed))

    @classmethod
    def from_env(cls, *, default_output_dir: str | Path | None = None) -> "AgentTraceSamplingPolicy":
        output_dir = Path(
            os.getenv("LEXA_AGENT_TRACE_DIR", "").strip()
            or default_output_dir
            or Path(__file__).resolve().parents[1] / "evals" / "results" / "traces"
        )
        allowed = _env_csv("LEXA_AGENT_TRACE_ALLOWED_SOURCES") or {"synthetic", "test", "eval", "fixture"}
        denied = _env_csv("LEXA_AGENT_TRACE_DENIED_SOURCES") or {"runtime", "production", "user"}
        return cls(
            enabled=env_flag("LEXA_AGENT_TRACE") and env_flag("LEXA_AGENT_TRACE_SAMPLING"),
            sample_rate=_env_float("LEXA_AGENT_TRACE_SAMPLE_RATE", 1.0),
            allowed_sources=allowed,
            denied_sources=denied,
            max_events_per_run=_env_int("LEXA_AGENT_TRACE_MAX_EVENTS", 100),
            max_metadata_chars=_env_int("LEXA_AGENT_TRACE_MAX_METADATA_CHARS", 160),
            require_synthetic_context=not env_flag("LEXA_AGENT_TRACE_ALLOW_REAL_CONTEXT"),
            output_dir=output_dir,
            redact_level=os.getenv("LEXA_AGENT_TRACE_REDACT_LEVEL", "strict").strip().lower() or "strict",
            seed=_env_optional_int("LEXA_AGENT_TRACE_SEED"),
        )

    def should_sample(self, *, source: str, synthetic_context: bool) -> bool:
        normalized_source = str(source or "").lower()
        if not self.enabled:
            return False
        if self.sample_rate <= 0:
            return False
        if self.require_synthetic_context and not synthetic_context:
            return False
        if normalized_source in self.denied_sources:
            return False
        if self.allowed_sources and normalized_source not in self.allowed_sources:
            return False
        if self.sample_rate >= 1:
            return True
        # Probabilistic sampling for intermediate rates (e.g. 0.5 -> ~50%).
        # Uses a dedicated RNG so eval runs stay reproducible (with a seed)
        # and decoupled from the process-wide random state.
        return self._rng.random() < self.sample_rate

    def safe_output_path(self, run_id: str) -> Path:
        output_path = (self.output_dir / f"{run_id}.jsonl").expanduser().resolve()
        if not trace_path_is_safe(output_path):
            raise ValueError("agent trace sampling output_dir must be ignored/safe")
        return output_path

    def sanitize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        sanitized = redacted_metadata(metadata or {})
        return _clip_value(sanitized, self.max_metadata_chars)

    def sanitize_summary(self, summary: Any) -> str:
        return redacted_summary(summary, max_chars=self.max_metadata_chars)


def _env_csv(name: str) -> set[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return set()
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def _env_float(name: str, default: float) -> float:
    """Parse a float env var, falling back to default on missing/invalid input.

    A typo like LEXA_AGENT_TRACE_SAMPLE_RATE=hoch must not crash the agent run.
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    """Parse an int env var, falling back to default on missing/invalid input."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_optional_int(name: str) -> int | None:
    """Parse an optional int env var, returning None on missing/invalid input.

    Used for the trace sampling seed: absent or malformed means "no fixed seed".
    """
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _clip_value(value: Any, max_chars: int) -> Any:
    if isinstance(value, dict):
        return {str(key): _clip_value(item, max_chars) for key, item in value.items()}
    if isinstance(value, list):
        return [_clip_value(item, max_chars) for item in value[:20]]
    if isinstance(value, str):
        return redacted_summary(value, max_chars=max_chars)
    return value
