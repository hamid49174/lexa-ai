"""Wake-word engine adapters for Lexa voice.

Modern assistants do not run full STT continuously for wake-word detection.
This module gives Lexa a local keyword-spotting boundary first, with the
existing STT phrase matcher kept as a compatibility fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
import logging
import os
from pathlib import Path
import re
from typing import Protocol

import numpy as np

from voice.config import (
    WAKE_ENGINE,
    WAKE_LEGACY_TRANSCRIPT_ENABLED,
    WAKE_OPENWAKEWORD_MODELS,
    WAKE_OPENWAKEWORD_AUTO_DOWNLOAD,
    WAKE_OPENWAKEWORD_PATIENCE,
    WAKE_OPENWAKEWORD_THRESHOLD,
    WAKE_OPENWAKEWORD_VAD_THRESHOLD,
    WAKE_PORCUPINE_ACCESS_KEY,
    WAKE_PORCUPINE_KEYWORD_PATHS,
    WAKE_PORCUPINE_KEYWORDS,
    WAKE_PORCUPINE_SENSITIVITY,
)

logger = logging.getLogger("lexa.wakeword.engine")


def _normalize_wake_text(text: str) -> list[str]:
    normalized = re.sub(r"[^\w]+", " ", str(text or "").lower(), flags=re.UNICODE)
    return [token for token in normalized.split() if token]


def _wake_phrase_span(text: str, phrases: list[str]) -> tuple[int, int] | None:
    tokens = _normalize_wake_text(text)
    if not tokens:
        return None
    matches: list[tuple[int, int, int]] = []
    for phrase in phrases:
        phrase_tokens = _normalize_wake_text(phrase)
        if not phrase_tokens:
            continue
        width = len(phrase_tokens)
        if width > len(tokens):
            continue
        for start in range(0, len(tokens) - width + 1):
            if tokens[start:start + width] == phrase_tokens:
                matches.append((start, start + width, width))
    if not matches:
        return None
    start, end, _width = sorted(matches, key=lambda item: (item[1], -item[2], item[0]))[0]
    return start, end


def _contains_wake_phrase(text: str, phrases: list[str]) -> bool:
    return _wake_phrase_span(text, phrases) is not None


def _command_after_wake_phrase(text: str, phrases: list[str]) -> str:
    tokens = _normalize_wake_text(text)
    span = _wake_phrase_span(text, phrases)
    if not span:
        return ""
    _start, end = span
    command_tokens = tokens[end:]
    while command_tokens and command_tokens[0] in {"bitte", "please"}:
        command_tokens = command_tokens[1:]
    return " ".join(command_tokens).strip()


@dataclass
class WakeDetection:
    detected: bool
    text: str = ""
    command: str = ""
    score: float = 0.0
    source: str = ""
    detail: dict = field(default_factory=dict)


class WakeWordEngine(Protocol):
    name: str
    uses_stt: bool

    def ensure_ready(self) -> bool:
        ...

    def detect(self, audio: np.ndarray, sample_rate: int, phrases: list[str]) -> WakeDetection:
        ...

    def status(self) -> dict:
        ...


class UnavailableWakeWordEngine:
    name = "wake_engine_unavailable"
    uses_stt = False

    def __init__(self, error: str, configured_mode: str = ""):
        self.error = error
        self.configured_mode = configured_mode

    def ensure_ready(self) -> bool:
        return False

    def detect(self, audio: np.ndarray, sample_rate: int, phrases: list[str]) -> WakeDetection:
        return WakeDetection(False, source=self.name, detail={"error": self.error})

    def status(self) -> dict:
        return {
            "name": self.name,
            "ready": False,
            "local": False,
            "uses_stt": False,
            "legacy": False,
            "configured_mode": self.configured_mode,
            "error": self.error,
            "detail": self.error,
        }


class TranscriptWakeWordEngine:
    """Explicit legacy mode only: transcribe a short window and match wake tokens."""

    name = "legacy_transcript_phrase_match"
    uses_stt = True

    def ensure_ready(self) -> bool:
        return WAKE_LEGACY_TRANSCRIPT_ENABLED

    def detect(self, audio: np.ndarray, sample_rate: int, phrases: list[str]) -> WakeDetection:
        if not self.ensure_ready():
            return WakeDetection(False, source=self.name, detail={"error": "Legacy transcript wake mode is disabled."})
        from voice.stt import fast_transcribe

        text = fast_transcribe(audio, sample_rate).lower().strip()
        if not text:
            return WakeDetection(False, source=self.name)
        detected = _contains_wake_phrase(text, phrases)
        return WakeDetection(
            detected=detected,
            text=text,
            command=_command_after_wake_phrase(text, phrases) if detected else "",
            source=self.name,
        )

    def status(self) -> dict:
        return {
            "name": self.name,
            "ready": self.ensure_ready(),
            "local": False,
            "uses_stt": True,
            "legacy": True,
            "error": "" if self.ensure_ready() else "Legacy transcript wake mode is disabled.",
            "detail": "Legacy fallback via short-window STT transcript matching. Not used by default.",
        }


class OpenWakeWordEngine:
    """Optional local ONNX keyword spotter via openWakeWord.

    Configure with:
      LEXA_WAKE_ENGINE=openwakeword
      LEXA_OPENWAKEWORD_MODELS=C:\\path\\lexa.onnx
    """

    name = "openwakeword"
    uses_stt = False

    def __init__(self, model_paths: list[str] | None = None, threshold: float = WAKE_OPENWAKEWORD_THRESHOLD):
        self.threshold = float(threshold)
        self.patience = max(0, int(WAKE_OPENWAKEWORD_PATIENCE))
        self.vad_threshold = float(WAKE_OPENWAKEWORD_VAD_THRESHOLD)
        self.auto_download = bool(WAKE_OPENWAKEWORD_AUTO_DOWNLOAD)
        self.model_refs = [p for p in (model_paths or _configured_model_refs()) if p]
        self.model_paths = [p for p in self.model_refs if _looks_like_model_path(p)]
        self.model_names = [_normalize_model_name(p) for p in self.model_refs if not _looks_like_model_path(p)]
        self._model = None
        self._error = ""
        self._labels: list[str] = []
        self._load_attempted = False

    def ensure_ready(self) -> bool:
        if self._model is None and not self._load_attempted:
            self._load()
        return self._model is not None

    def _load(self):
        self._load_attempted = True
        if importlib.util.find_spec("openwakeword") is None:
            self._error = "openWakeWord package not installed."
            return
        if not self.model_refs:
            self._error = "No openWakeWord model configured. Set LEXA_OPENWAKEWORD_MODELS, e.g. 'alexa' or a custom Lexa .onnx path."
            return
        missing = [path for path in self.model_paths if not Path(path).exists()]
        if missing:
            self._error = f"openWakeWord model file missing: {missing[0]}"
            return
        try:
            from openwakeword.model import Model
            if self.auto_download and self.model_names:
                from openwakeword.utils import download_models
                download_models(model_names=self.model_names)

            self._model = Model(
                wakeword_models=list(self.model_refs),
                inference_framework="onnx",
                vad_threshold=self.vad_threshold,
            )
            self._labels = list(getattr(self._model, "models", {}).keys()) or [
                Path(path).stem if _looks_like_model_path(path) else _normalize_model_name(path)
                for path in self.model_refs
            ]
            self._error = ""
        except Exception as e:
            self._model = None
            self._error = str(e)
            logger.warning("openWakeWord load failed: %s", e)

    def detect(self, audio: np.ndarray, sample_rate: int, phrases: list[str]) -> WakeDetection:
        if self._model is None:
            return WakeDetection(False, source=self.name, detail={"error": self._error})
        if sample_rate != 16000:
            return WakeDetection(False, source=self.name, detail={"error": "openWakeWord expects 16kHz audio."})
        pcm = np.asarray(audio, dtype=np.float32)
        pcm = np.clip(pcm, -1.0, 1.0)
        pcm16 = (pcm * 32767).astype(np.int16)
        try:
            threshold = {label: self.threshold for label in self._labels}
            patience = {label: self.patience for label in self._labels if self.patience > 1}
            if patience:
                scores = self._model.predict(pcm16, patience=patience, threshold=threshold)
            else:
                scores = self._model.predict(pcm16)
        except Exception as e:
            self._error = str(e)
            return WakeDetection(False, source=self.name, detail={"error": self._error})
        if not isinstance(scores, dict) or not scores:
            return WakeDetection(False, source=self.name, detail={"scores": scores})
        label, score = max(scores.items(), key=lambda item: float(item[1] or 0.0))
        score = float(score or 0.0)
        detected = score >= self.threshold
        return WakeDetection(
            detected=detected,
            text="lexa" if detected else "",
            score=score,
            source=self.name,
            detail={"label": label, "threshold": self.threshold, "scores": scores},
        )

    def status(self) -> dict:
        return {
            "name": self.name,
            "ready": self._model is not None,
            "local": True,
            "uses_stt": False,
            "legacy": False,
            "threshold": self.threshold,
            "patience": self.patience,
            "vad_threshold": self.vad_threshold,
            "auto_download": self.auto_download,
            "model_refs": self.model_refs,
            "model_names": self.model_names,
            "models": self.model_paths,
            "labels": self._labels,
            "load_attempted": self._load_attempted,
            "error": self._error,
            "detail": "Local ONNX keyword spotting via openWakeWord.",
        }


class PorcupineWakeWordEngine:
    """Optional commercial/local keyword engine via Picovoice Porcupine."""

    name = "porcupine"
    uses_stt = False

    def __init__(self):
        self.access_key = WAKE_PORCUPINE_ACCESS_KEY.strip()
        self.keyword_paths = _split_config_list(WAKE_PORCUPINE_KEYWORD_PATHS)
        self.keywords = _split_config_list(WAKE_PORCUPINE_KEYWORDS)
        self.sensitivity = float(WAKE_PORCUPINE_SENSITIVITY)
        self._handle = None
        self._error = ""
        self._load_attempted = False

    def ensure_ready(self) -> bool:
        if self._handle is None and not self._load_attempted:
            self._load()
        return self._handle is not None

    def _load(self):
        self._load_attempted = True
        if importlib.util.find_spec("pvporcupine") is None:
            self._error = "pvporcupine package not installed."
            return
        if not self.access_key:
            self._error = "Porcupine requires LEXA_PORCUPINE_ACCESS_KEY or PICOVOICE_ACCESS_KEY."
            return
        if not self.keyword_paths and not self.keywords:
            self._error = "Porcupine requires LEXA_PORCUPINE_KEYWORD_PATHS for Lexa, or built-in LEXA_PORCUPINE_KEYWORDS."
            return
        missing = [path for path in self.keyword_paths if not Path(path).exists()]
        if missing:
            self._error = f"Porcupine keyword file missing: {missing[0]}"
            return
        try:
            import pvporcupine
            kwargs = {
                "access_key": self.access_key,
                "sensitivities": [self.sensitivity] * max(1, len(self.keyword_paths) or len(self.keywords)),
            }
            if self.keyword_paths:
                kwargs["keyword_paths"] = self.keyword_paths
            if self.keywords:
                kwargs["keywords"] = self.keywords
            self._handle = pvporcupine.create(**kwargs)
            self._error = ""
        except Exception as e:
            self._handle = None
            self._error = str(e)
            logger.warning("Porcupine load failed: %s", e)

    def detect(self, audio: np.ndarray, sample_rate: int, phrases: list[str]) -> WakeDetection:
        if self._handle is None:
            return WakeDetection(False, source=self.name, detail={"error": self._error})
        if sample_rate != getattr(self._handle, "sample_rate", sample_rate):
            return WakeDetection(False, source=self.name, detail={"error": "Porcupine sample-rate mismatch."})
        pcm = np.asarray(audio, dtype=np.float32)
        pcm = np.clip(pcm, -1.0, 1.0)
        pcm16 = (pcm * 32767).astype(np.int16)
        frame_length = int(getattr(self._handle, "frame_length", 512) or 512)
        for start in range(0, max(0, len(pcm16) - frame_length + 1), frame_length):
            frame = pcm16[start:start + frame_length]
            try:
                index = self._handle.process(frame)
            except Exception as e:
                self._error = str(e)
                return WakeDetection(False, source=self.name, detail={"error": self._error})
            if index >= 0:
                label = (
                    Path(self.keyword_paths[index]).stem
                    if self.keyword_paths and index < len(self.keyword_paths)
                    else (self.keywords[index] if index < len(self.keywords) else "wake")
                )
                return WakeDetection(
                    True,
                    text="lexa",
                    score=1.0,
                    source=self.name,
                    detail={"label": label, "index": index},
                )
        return WakeDetection(False, source=self.name)

    def status(self) -> dict:
        return {
            "name": self.name,
            "ready": self._handle is not None,
            "local": True,
            "uses_stt": False,
            "legacy": False,
            "keyword_paths": self.keyword_paths,
            "keywords": self.keywords,
            "sensitivity": self.sensitivity,
            "load_attempted": self._load_attempted,
            "error": self._error,
            "detail": "Local keyword spotting via Picovoice Porcupine.",
        }


def _split_config_list(raw: str) -> list[str]:
    return [part.strip().strip('"') for part in re.split(r"[;,]", raw or "") if part.strip()]


def _configured_model_refs() -> list[str]:
    raw = WAKE_OPENWAKEWORD_MODELS or os.environ.get("LEXA_OPENWAKEWORD_MODELS", "")
    return _split_config_list(raw)


def _looks_like_model_path(value: str) -> bool:
    text = str(value or "").strip()
    return bool(re.search(r"\.(onnx|tflite)$", text, flags=re.IGNORECASE) or "\\" in text or "/" in text)


def _normalize_model_name(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def create_default_wakeword_engine() -> WakeWordEngine:
    mode = (os.environ.get("LEXA_WAKE_ENGINE") or WAKE_ENGINE or "openwakeword").strip().lower()
    if mode in {"openwakeword", "local", "auto"}:
        return OpenWakeWordEngine()
    if mode == "porcupine":
        return PorcupineWakeWordEngine()
    if mode in {"legacy", "legacy_transcript", "transcript"}:
        if WAKE_LEGACY_TRANSCRIPT_ENABLED:
            return TranscriptWakeWordEngine()
        return UnavailableWakeWordEngine(
            "Legacy transcript wake mode is disabled. Set LEXA_WAKE_LEGACY_TRANSCRIPT_ENABLED=1 only for debugging.",
            configured_mode=mode,
        )
    return UnavailableWakeWordEngine(f"Unknown wake engine '{mode}'. Use openwakeword or porcupine.", configured_mode=mode)


def get_wakeword_engine_capabilities() -> dict:
    openwakeword_installed = importlib.util.find_spec("openwakeword") is not None
    porcupine_installed = importlib.util.find_spec("pvporcupine") is not None
    configured_models = _configured_model_refs()
    return {
        "target": "siri_style_local_keyword_spotting",
        "configured_mode": (os.environ.get("LEXA_WAKE_ENGINE") or WAKE_ENGINE or "openwakeword"),
        "openwakeword_installed": openwakeword_installed,
        "openwakeword_models_configured": bool(configured_models),
        "openwakeword_models": configured_models,
        "openwakeword_auto_download": bool(WAKE_OPENWAKEWORD_AUTO_DOWNLOAD),
        "porcupine_installed": porcupine_installed,
        "porcupine_configured": bool(WAKE_PORCUPINE_ACCESS_KEY and (WAKE_PORCUPINE_KEYWORD_PATHS or WAKE_PORCUPINE_KEYWORDS)),
        "legacy_transcript_enabled": bool(WAKE_LEGACY_TRANSCRIPT_ENABLED),
        "legacy": TranscriptWakeWordEngine().status(),
        "recommendation": (
            "Use a custom Lexa openWakeWord ONNX model for production-quality 'Lexa' detection."
            if openwakeword_installed
            else "Install openwakeword or configure Porcupine with a custom Lexa keyword model."
        ),
    }
