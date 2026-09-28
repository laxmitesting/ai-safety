"""src/tools/qdrant_client.py: Embedded Qdrant client and local embedding generator."""

import atexit
from typing import Optional
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from configs.settings import EMBEDDING_MODEL, QDRANT_STORAGE_DIR

# 1. Initialize local embedding model (CPU-only)
_encoder = SentenceTransformer(EMBEDDING_MODEL)

# 2. Module-level reference to hold the open local storage instance
_client: Optional[QdrantClient] = None


def get_embedding(text: str) -> list[float]:
    """Generates a dense vector for text using the configured model (384 dimensions)."""
    return _encoder.encode(text).tolist()


def close_qdrant_client() -> None:
    """Explicitly closes the storage backend before interpreter shutdown."""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


def get_qdrant_client() -> QdrantClient:
    """Returns the local embedded Qdrant instance, reusing the existing connection."""
    global _client
    if _client is None:
        QDRANT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _client = QdrantClient(path=str(QDRANT_STORAGE_DIR))
        # Ensure client is gracefully closed before Python tears down sys.meta_path
        atexit.register(close_qdrant_client)
    return _client