"""Lexa AI — Embedding Engine (Phase 42: Semantic Memory)
Multi-provider text embeddings with caching and graceful fallback.

Provider chain:
1. OpenAI text-embedding-3-small (1536 dims, ~$0.02/1M tokens)
2. Local TF-IDF vectorizer with numpy (no extra dependencies, offline-capable)
3. Falls back gracefully if nothing works — FTS5 keyword search still works.

The embedding engine is designed to be transparent: memory.py calls embed_text()
and gets a vector back. It doesn't need to know which provider is active.
"""

import hashlib
import json
import logging
import struct
import threading
import time
from typing import Optional

import numpy as np

logger = logging.getLogger("lexa.embeddings")

# ══════════════════════════════════════════════════
#  CONFIGURATION
# ══════════════════════════════════════════════════

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_EMBEDDING_DIMS = 1536
LOCAL_EMBEDDING_DIMS = 256       # TF-IDF vocabulary size for local fallback
EMBEDDING_CACHE_MAX = 500
EMBEDDING_CACHE_TTL = 3600       # 1 hour

# ══════════════════════════════════════════════════
#  CACHE (thread-safe, LRU-like with TTL)
# ══════════════════════════════════════════════════

_cache: dict[str, tuple[list[float], float]] = {}  # hash -> (vector, timestamp)
_cache_lock = threading.Lock()


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]


def _cache_get(text: str) -> Optional[list[float]]:
    key = _cache_key(text)
    with _cache_lock:
        entry = _cache.get(key)
        if entry:
            vec, ts = entry
            if time.time() - ts < EMBEDDING_CACHE_TTL:
                return vec
            del _cache[key]
    return None


def _cache_put(text: str, vector: list[float]) -> None:
    key = _cache_key(text)
    with _cache_lock:
        if len(_cache) >= EMBEDDING_CACHE_MAX:
            # Evict oldest 20%
            sorted_keys = sorted(_cache, key=lambda k: _cache[k][1])
            for k in sorted_keys[:EMBEDDING_CACHE_MAX // 5]:
                del _cache[k]
        _cache[key] = (vector, time.time())


def cache_stats() -> dict:
    """Return cache statistics."""
    with _cache_lock:
        return {"size": len(_cache), "max": EMBEDDING_CACHE_MAX}


# ══════════════════════════════════════════════════
#  PROVIDER DETECTION
# ══════════════════════════════════════════════════

_active_provider: Optional[str] = None
_provider_lock = threading.Lock()


def _detect_provider() -> str:
    """Detect the best available embedding provider."""
    global _active_provider
    with _provider_lock:
        if _active_provider:
            return _active_provider

        # Try OpenAI
        try:
            from backend.ai_engine import _get_openai_client
            client = _get_openai_client()
            if client:
                _active_provider = "openai"
                logger.info("Embedding provider: OpenAI (text-embedding-3-small)")
                return "openai"
        except Exception:
            pass

        # Try getting OpenAI API key directly
        try:
            import keyring
            key = keyring.get_password("lexa-ai", "openai_api_key")
            if not key:
                import os
                key = os.environ.get("OPENAI_API_KEY", "")
            if key:
                _active_provider = "openai"
                logger.info("Embedding provider: OpenAI (via API key)")
                return "openai"
        except Exception:
            pass

        # Fallback to local TF-IDF
        _active_provider = "local"
        logger.info("Embedding provider: Local TF-IDF (offline, no API needed)")
        return "local"


def get_provider() -> str:
    """Return the active embedding provider name."""
    return _detect_provider()


def reset_provider() -> None:
    """Force re-detection of the embedding provider."""
    global _active_provider
    with _provider_lock:
        _active_provider = None


# ══════════════════════════════════════════════════
#  OPENAI EMBEDDINGS
# ══════════════════════════════════════════════════

def _embed_openai(text: str) -> Optional[list[float]]:
    """Get embedding from OpenAI API."""
    try:
        import openai
        import keyring
        import os

        api_key = None
        try:
            api_key = keyring.get_password("lexa-ai", "openai_api_key")
        except Exception:
            pass
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None

        client = openai.OpenAI(api_key=api_key)
        response = client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=text[:8000],  # OpenAI limit
        )
        return response.data[0].embedding
    except Exception as e:
        logger.warning(f"OpenAI embedding failed: {e}")
        return None


def _embed_openai_batch(texts: list[str]) -> Optional[list[list[float]]]:
    """Get embeddings for multiple texts from OpenAI API (batch)."""
    try:
        import openai
        import keyring
        import os

        api_key = None
        try:
            api_key = keyring.get_password("lexa-ai", "openai_api_key")
        except Exception:
            pass
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None

        client = openai.OpenAI(api_key=api_key)
        # OpenAI supports batch embeddings (up to 2048 inputs)
        truncated = [t[:8000] for t in texts]
        response = client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=truncated,
        )
        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda d: d.index)
        return [d.embedding for d in sorted_data]
    except Exception as e:
        logger.warning(f"OpenAI batch embedding failed: {e}")
        return None


# ══════════════════════════════════════════════════
#  LOCAL TF-IDF EMBEDDINGS (numpy-only, no extra deps)
# ══════════════════════════════════════════════════

# Global vocabulary for consistent TF-IDF vectors
_vocabulary: dict[str, int] = {}
_vocab_lock = threading.Lock()
_IDF_DAMPENING = 1.0  # Smoothing factor


def _tokenize(text: str) -> list[str]:
    """Simple German-aware tokenizer: lowercase, split, strip punctuation."""
    import re
    text = text.lower()
    # Split on non-alphanumeric, keep umlauts
    tokens = re.findall(r'[a-zäöüß]+', text)
    # Remove very short tokens
    return [t for t in tokens if len(t) >= 2]


def _build_tfidf_vector(tokens: list[str], dim: int = LOCAL_EMBEDDING_DIMS) -> list[float]:
    """Build a fixed-size TF-IDF-like vector using hashing trick.

    Uses the hashing trick to map tokens to a fixed-size vector space,
    avoiding the need for a pre-built vocabulary. Each token is hashed
    to a bucket index, and its TF weight is accumulated.
    The resulting vector is L2-normalized.
    """
    vec = np.zeros(dim, dtype=np.float64)

    if not tokens:
        return vec.tolist()

    # Term frequencies
    tf: dict[str, int] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1

    max_tf = max(tf.values()) if tf else 1

    for token, count in tf.items():
        # Hash to bucket (deterministic)
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        bucket = h % dim
        # Sign hash for variance reduction (feature hashing trick)
        sign = 1 if (h // dim) % 2 == 0 else -1
        # Normalized TF (augmented frequency to prevent bias toward longer docs)
        normalized_tf = 0.5 + 0.5 * (count / max_tf)
        vec[bucket] += sign * normalized_tf

    # L2 normalize
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec.tolist()


def _embed_local(text: str) -> list[float]:
    """Generate a local TF-IDF embedding using the hashing trick."""
    tokens = _tokenize(text)
    return _build_tfidf_vector(tokens)


def _embed_local_batch(texts: list[str]) -> list[list[float]]:
    """Generate local embeddings for multiple texts."""
    return [_embed_local(t) for t in texts]


# ══════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════

def embed_text(text: str) -> Optional[list[float]]:
    """Get embedding vector for a text string.

    Returns a list of floats, or None if embedding fails entirely.
    Uses cache to avoid redundant computations.
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Check cache
    cached = _cache_get(text)
    if cached:
        return cached

    provider = _detect_provider()
    vector = None

    if provider == "openai":
        vector = _embed_openai(text)
        if vector is None:
            # Fallback to local
            vector = _embed_local(text)
    else:
        vector = _embed_local(text)

    if vector:
        _cache_put(text, vector)

    return vector


def embed_batch(texts: list[str], batch_size: int = 100) -> list[Optional[list[float]]]:
    """Get embeddings for multiple texts efficiently.

    Uses batch API when available (OpenAI supports up to 2048 inputs).
    Returns a list of vectors (same order as input), None for failures.
    """
    if not texts:
        return []

    results: list[Optional[list[float]]] = [None] * len(texts)

    # Check cache first
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []
    for i, text in enumerate(texts):
        if not text or not text.strip():
            continue
        cached = _cache_get(text.strip())
        if cached:
            results[i] = cached
        else:
            uncached_indices.append(i)
            uncached_texts.append(text.strip())

    if not uncached_texts:
        return results

    provider = _detect_provider()

    # Process in batches
    for start in range(0, len(uncached_texts), batch_size):
        batch = uncached_texts[start:start + batch_size]
        batch_indices = uncached_indices[start:start + batch_size]

        vectors = None
        if provider == "openai":
            vectors = _embed_openai_batch(batch)
        if vectors is None:
            vectors = _embed_local_batch(batch)

        if vectors:
            for idx, vec in zip(batch_indices, vectors):
                results[idx] = vec
                _cache_put(texts[idx].strip(), vec)

    return results


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns a float between -1.0 and 1.0.
    Optimized with numpy for speed.
    """
    if not a or not b:
        return 0.0

    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)

    # Handle dimension mismatch (different providers)
    if len(va) != len(vb):
        return 0.0

    dot = np.dot(va, vb)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot / (norm_a * norm_b))


# ══════════════════════════════════════════════════
#  VECTOR SERIALIZATION (for SQLite BLOB storage)
# ══════════════════════════════════════════════════

def vector_to_blob(vector: list[float]) -> bytes:
    """Serialize a float vector to bytes for SQLite BLOB storage.

    Uses struct.pack for compact binary representation.
    Format: 4-byte header (dimension count as uint32) + float32 values.
    """
    dim = len(vector)
    # Header: dimension as uint32 + float32 values
    return struct.pack(f"<I{dim}f", dim, *vector)


def blob_to_vector(data: bytes) -> Optional[list[float]]:
    """Deserialize a BLOB back to a float vector."""
    if not data or len(data) < 4:
        return None
    try:
        dim = struct.unpack("<I", data[:4])[0]
        expected_size = 4 + dim * 4
        if len(data) < expected_size:
            return None
        values = struct.unpack(f"<{dim}f", data[4:expected_size])
        return list(values)
    except (struct.error, ValueError):
        return None


# ══════════════════════════════════════════════════
#  STATUS
# ══════════════════════════════════════════════════

def get_embedding_status() -> dict:
    """Return embedding system status."""
    provider = _detect_provider()
    cs = cache_stats()
    return {
        "provider": provider,
        "model": OPENAI_EMBEDDING_MODEL if provider == "openai" else "local-tfidf",
        "dimensions": OPENAI_EMBEDDING_DIMS if provider == "openai" else LOCAL_EMBEDDING_DIMS,
        "cache_size": cs["size"],
        "cache_max": cs["max"],
    }
