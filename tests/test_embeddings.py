"""Tests for backend/embeddings.py and Phase 42 semantic memory integration."""

import struct
import pytest


# ═══════════════════════════════════════════════════
#  Embedding Engine Core
# ═══════════════════════════════════════════════════

class TestLocalEmbeddings:
    """Test local TF-IDF embedding engine (no API key needed)."""

    def test_embed_text_returns_vector(self):
        from backend.embeddings import embed_text, reset_provider
        reset_provider()  # Force re-detection
        vector = embed_text("Hallo Welt, dies ist ein Test")
        assert vector is not None
        assert isinstance(vector, list)
        assert len(vector) > 0
        assert all(isinstance(v, float) for v in vector)

    def test_embed_text_empty_returns_none(self):
        from backend.embeddings import embed_text
        assert embed_text("") is None
        assert embed_text("   ") is None

    def test_embed_text_consistent(self):
        """Same input should return same output."""
        from backend.embeddings import embed_text
        v1 = embed_text("Python Programmierung lernen")
        v2 = embed_text("Python Programmierung lernen")
        assert v1 == v2

    def test_embed_text_different_texts_differ(self):
        """Different texts should produce different vectors."""
        from backend.embeddings import embed_text
        v1 = embed_text("Python Programmierung lernen")
        v2 = embed_text("Kuchen backen Rezept")
        assert v1 != v2

    def test_embed_local_dimensions(self):
        from backend.embeddings import _embed_local, LOCAL_EMBEDDING_DIMS
        vec = _embed_local("Test embedding dimensionen")
        assert len(vec) == LOCAL_EMBEDDING_DIMS

    def test_embed_local_normalized(self):
        """Local vectors should be L2-normalized (unit length)."""
        import math
        from backend.embeddings import _embed_local
        vec = _embed_local("Normalisierter Vektor Test")
        norm = math.sqrt(sum(v * v for v in vec))
        assert abs(norm - 1.0) < 0.01  # Should be ~1.0

    def test_embed_local_empty_tokens(self):
        """Empty/stop-word-only text should return zero vector."""
        from backend.embeddings import _embed_local
        vec = _embed_local("a b c")  # All tokens < 2 chars
        # Should be all zeros (no tokens to hash)
        assert all(v == 0.0 for v in vec)


class TestTokenizer:
    def test_tokenize_german(self):
        from backend.embeddings import _tokenize
        tokens = _tokenize("Hallo Welt, dies ist ein schöner Tag!")
        assert "hallo" in tokens
        assert "welt" in tokens
        assert "schöner" in tokens

    def test_tokenize_short_removed(self):
        from backend.embeddings import _tokenize
        tokens = _tokenize("a b cd ef")
        assert "a" not in tokens
        assert "b" not in tokens
        assert "cd" in tokens
        assert "ef" in tokens

    def test_tokenize_umlauts(self):
        from backend.embeddings import _tokenize
        tokens = _tokenize("Ärger über Größe und Gemüse")
        assert "über" in tokens
        assert "größe" in tokens


class TestBuildTfidfVector:
    def test_hashing_deterministic(self):
        from backend.embeddings import _build_tfidf_vector
        v1 = _build_tfidf_vector(["python", "test", "code"])
        v2 = _build_tfidf_vector(["python", "test", "code"])
        assert v1 == v2

    def test_empty_tokens_zero_vector(self):
        from backend.embeddings import _build_tfidf_vector
        vec = _build_tfidf_vector([])
        assert all(v == 0.0 for v in vec)

    def test_different_tokens_different_vectors(self):
        from backend.embeddings import _build_tfidf_vector
        v1 = _build_tfidf_vector(["python", "code"])
        v2 = _build_tfidf_vector(["kuchen", "backen"])
        assert v1 != v2


# ═══════════════════════════════════════════════════
#  Cosine Similarity
# ═══════════════════════════════════════════════════

class TestCosineSimilarity:
    def test_identical_vectors(self):
        from backend.embeddings import cosine_similarity
        vec = [1.0, 2.0, 3.0]
        sim = cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        from backend.embeddings import cosine_similarity
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        sim = cosine_similarity(a, b)
        assert abs(sim) < 0.001

    def test_opposite_vectors(self):
        from backend.embeddings import cosine_similarity
        a = [1.0, 2.0, 3.0]
        b = [-1.0, -2.0, -3.0]
        sim = cosine_similarity(a, b)
        assert abs(sim - (-1.0)) < 0.001

    def test_empty_vectors(self):
        from backend.embeddings import cosine_similarity
        assert cosine_similarity([], []) == 0.0
        assert cosine_similarity([], [1.0]) == 0.0

    def test_dimension_mismatch_returns_zero(self):
        from backend.embeddings import cosine_similarity
        assert cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0

    def test_zero_vector_returns_zero(self):
        from backend.embeddings import cosine_similarity
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_similar_texts_high_similarity(self):
        """Semantically similar texts should have high cosine similarity."""
        from backend.embeddings import embed_text, cosine_similarity
        v1 = embed_text("Python Programmierung lernen")
        v2 = embed_text("Python programmieren lernen Anfänger")
        sim = cosine_similarity(v1, v2)
        assert sim > 0.3  # Should be reasonably similar (shared tokens)


# ═══════════════════════════════════════════════════
#  Vector Serialization (BLOB)
# ═══════════════════════════════════════════════════

class TestVectorSerialization:
    def test_roundtrip(self):
        from backend.embeddings import vector_to_blob, blob_to_vector
        original = [1.0, 2.5, -3.14, 0.0, 42.0]
        blob = vector_to_blob(original)
        restored = blob_to_vector(blob)
        assert restored is not None
        assert len(restored) == len(original)
        for a, b in zip(original, restored):
            assert abs(a - b) < 0.001

    def test_blob_format(self):
        from backend.embeddings import vector_to_blob
        vec = [1.0, 2.0, 3.0]
        blob = vector_to_blob(vec)
        # Header: 4 bytes (uint32 dim=3) + 3 * 4 bytes (float32)
        assert len(blob) == 4 + 3 * 4
        dim = struct.unpack("<I", blob[:4])[0]
        assert dim == 3

    def test_blob_to_vector_none_input(self):
        from backend.embeddings import blob_to_vector
        assert blob_to_vector(None) is None
        assert blob_to_vector(b"") is None
        assert blob_to_vector(b"\x00") is None

    def test_blob_to_vector_truncated(self):
        from backend.embeddings import blob_to_vector
        # Header says dim=100 but only 4 bytes of data
        bad_blob = struct.pack("<I", 100) + b"\x00\x00\x00\x00"
        assert blob_to_vector(bad_blob) is None

    def test_large_vector_roundtrip(self):
        from backend.embeddings import vector_to_blob, blob_to_vector, LOCAL_EMBEDDING_DIMS
        vec = [float(i) / LOCAL_EMBEDDING_DIMS for i in range(LOCAL_EMBEDDING_DIMS)]
        blob = vector_to_blob(vec)
        restored = blob_to_vector(blob)
        assert len(restored) == LOCAL_EMBEDDING_DIMS


# ═══════════════════════════════════════════════════
#  Cache
# ═══════════════════════════════════════════════════

class TestEmbeddingCache:
    def test_cache_hit(self):
        from backend.embeddings import _cache_put, _cache_get
        _cache_put("test cache hit", [1.0, 2.0, 3.0])
        result = _cache_get("test cache hit")
        assert result == [1.0, 2.0, 3.0]

    def test_cache_miss(self):
        from backend.embeddings import _cache_get
        result = _cache_get("nonexistent_key_xyz_12345")
        assert result is None

    def test_cache_stats(self):
        from backend.embeddings import cache_stats
        stats = cache_stats()
        assert "size" in stats
        assert "max" in stats
        assert isinstance(stats["size"], int)


# ═══════════════════════════════════════════════════
#  Provider Detection
# ═══════════════════════════════════════════════════

class TestProviderDetection:
    def test_get_provider_returns_string(self):
        from backend.embeddings import get_provider
        provider = get_provider()
        assert provider in ("openai", "local")

    def test_reset_provider(self):
        from backend.embeddings import reset_provider, _active_provider, get_provider
        reset_provider()
        # After reset, next call re-detects
        provider = get_provider()
        assert provider in ("openai", "local")

    def test_get_embedding_status(self):
        from backend.embeddings import get_embedding_status
        status = get_embedding_status()
        assert "provider" in status
        assert "model" in status
        assert "dimensions" in status
        assert "cache_size" in status


# ═══════════════════════════════════════════════════
#  Batch Embeddings
# ═══════════════════════════════════════════════════

class TestBatchEmbeddings:
    def test_embed_batch_empty(self):
        from backend.embeddings import embed_batch
        assert embed_batch([]) == []

    def test_embed_batch_multiple(self):
        from backend.embeddings import embed_batch
        results = embed_batch(["Hallo Welt", "Python Code", "Lexa AI"])
        assert len(results) == 3
        assert all(r is not None for r in results)

    def test_embed_batch_with_empty_strings(self):
        from backend.embeddings import embed_batch
        results = embed_batch(["Hallo", "", "Welt"])
        assert len(results) == 3
        assert results[0] is not None
        assert results[1] is None  # Empty string
        assert results[2] is not None


# ═══════════════════════════════════════════════════
#  Memory Integration (Phase 42 semantic search)
# ═══════════════════════════════════════════════════

class TestMemorySemanticSearch:
    def test_search_semantic_empty_query(self):
        """Empty query should fall back gracefully."""
        from backend.memory import search_memory_semantic
        results = search_memory_semantic("")
        assert isinstance(results, list)

    def test_search_semantic_returns_list(self):
        from backend.memory import search_memory_semantic
        results = search_memory_semantic("Python lernen")
        assert isinstance(results, list)

    def test_get_embedding_stats_structure(self):
        from backend.memory import get_embedding_stats
        stats = get_embedding_stats()
        assert "total_memories" in stats
        assert "indexed_memories" in stats
        assert "unindexed_memories" in stats
        assert "coverage_pct" in stats


class TestMemoryAutoEmbed:
    def test_add_memory_does_not_crash_with_embedding(self):
        """add_memory should work even when embedding is enabled."""
        from backend.memory import add_memory
        # This should not raise even if embedding fails
        result = add_memory("Test embedding auto-embed 42xyz", category="test", importance=1)
        assert isinstance(result, str)

    def test_embed_memory_row_returns_bool(self):
        from backend.memory import _embed_memory_row, _get_db
        db = _get_db()
        # Try to embed a non-existent row — should return False gracefully
        result = _embed_memory_row(db, 999999, "test content")
        # Either True (embedded + updated 0 rows) or True (embedded successfully)
        assert isinstance(result, bool)


class TestReindexEmbeddings:
    def test_reindex_returns_dict(self):
        from backend.memory import reindex_embeddings
        result = reindex_embeddings(batch_size=10)
        assert isinstance(result, dict)
        assert "total" in result
        assert "status" in result

    def test_reindex_complete_status(self):
        """After reindex, status should be 'complete'."""
        from backend.memory import reindex_embeddings
        result = reindex_embeddings(batch_size=10)
        assert result["status"] == "complete"


# ═══════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════

class TestEmbeddingConfig:
    def test_config_values_exist(self):
        from backend.config import EMBEDDING_ENABLED, EMBEDDING_PROVIDER, EMBEDDING_REINDEX_BATCH
        assert isinstance(EMBEDDING_ENABLED, bool)
        assert EMBEDDING_PROVIDER in ("auto", "openai", "local")
        assert isinstance(EMBEDDING_REINDEX_BATCH, int)
        assert EMBEDDING_REINDEX_BATCH > 0
