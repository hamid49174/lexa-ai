"""Controlled trace sampling for synthetic Lexa agent runs.

Runtime traces are useful for replay evals, but unsafe if they capture real
conversation, memory, clipboard, or OS content. This module keeps sampling
explicit, test/synthetic scoped, bounded, and directed only at ignored paths.
"""

from __future__ import annotations

import os
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_rate", max(0.0, min(1.0, float(self.sample_rate))))
        object.__setattr__(self, "max_events_per_run", max(0, int(self.max_events_per_run)))
        object.__setattr__(self, "max_metadata_chars", max(32, int(self.max_metadata_chars)))
        object.__setattr__(self, "allowed_sources", {str(source).lower() for source in self.allowed_sources})
        object.__setattr__(self, "denied_sources", {str(source).lower() for source in self.denied_sources})
        object.__setattr__(self, "output_dir", Path(self.output_dir).expanduser())

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
            sample_rate=float(os.getenv("LEXA_AGENT_TRACE_SAMPLE_RATE", "1") or 1),
            allowed_sources=allowed,
            denied_sources=denied,
            max_events_per_run=int(os.getenv("LEXA_AGENT_TRACE_MAX_EVENTS", "100") or 100),
            max_metadata_chars=int(os.getenv("LEXA_AGENT_TRACE_MAX_METADATA_CHARS", "160") or 160),
            require_synthetic_context=not env_flag("LEXA_AGENT_TRACE_ALLOW_REAL_CONTEXT"),
            output_dir=output_dir,
            redact_level=os.getenv("LEXA_AGENT_TRACE_REDACT_LEVEL", "strict").strip().lower() or "strict",
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
        return self.sample_rate >= 1

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


def _clip_value(value: Any, max_chars: int) -> Any:
    if isinstance(value, dict):
        return {str(key): _clip_value(item, max_chars) for key, item in value.items()}
    if isinstance(value, list):
        return [_clip_value(item, max_chars) for item in value[:20]]
    if isinstance(value, str):
        return redacted_summary(value, max_chars=max_chars)
    return value
