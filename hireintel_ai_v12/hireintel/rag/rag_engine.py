"""
RAG Engine - ChromaDB
FIX: RustBindingsAPI error on Windows — client cached using st.cache_resource
     so it is created ONCE per session, never recreated on every call.
FIX 4: Resumes persist and reusable across sessions
FIX 5: Duplicate detection - same resume not stored twice
FIX 6: Delete individual resumes from UI
"""
import os
import hashlib
import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from config import CHROMA_PATH

# ── Single shared client — fixes RustBindingsAPI error on Windows ──────────
_CHROMA_CLIENT = None

def _client():
    """
    Return a single persistent ChromaDB client for the whole process.
    Creating a new PersistentClient on every call causes the RustBindingsAPI
    'bindings' error on Windows because the old client's destructor fires
    while the new one is being initialised.
    """
    global _CHROMA_CLIENT
    if _CHROMA_CLIENT is None:
        _CHROMA_CLIENT = chromadb.PersistentClient(path=CHROMA_PATH)
    return _CHROMA_CLIENT


def _emb():
    return DefaultEmbeddingFunction()


def resume_col():
    return _client().get_or_create_collection(
        "resumes",
        embedding_function=_emb(),
        metadata={"hnsw:space": "cosine"},
    )


def jd_col():
    return _client().get_or_create_collection(
        "job_descriptions",
        embedding_function=_emb(),
        metadata={"hnsw:space": "cosine"},
    )


def _id(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


# ── FIX 5: duplicate check ──────────────────────────────────────────────────
def resume_exists(filename: str) -> bool:
    """Return True if a resume with this filename is already stored."""
    try:
        result = resume_col().get(ids=[_id(filename)])
        return len(result["ids"]) > 0
    except Exception:
        return False


# ── upsert resume ───────────────────────────────────────────────────────────
def upsert_resume(filename: str, text: str, extra_meta: dict = None) -> dict:
    """
    FIX 5 — returns:
      { "stored": True,  "duplicate": False, "id": str }  — new entry saved
      { "stored": False, "duplicate": True,  "id": str }  — already existed, skipped
    """
    doc_id = _id(filename)
    col    = resume_col()

    # duplicate check
    try:
        existing = col.get(ids=[doc_id])
        if len(existing["ids"]) > 0:
            return {"stored": False, "duplicate": True,
                    "id": doc_id, "filename": filename}
    except Exception:
        pass

    meta = {"filename": filename, **(extra_meta or {})}
    col.upsert(ids=[doc_id], documents=[text[:8000]], metadatas=[meta])
    return {"stored": True, "duplicate": False, "id": doc_id, "filename": filename}


# ── upsert JD ───────────────────────────────────────────────────────────────
def upsert_jd(title: str, text: str, extra_meta: dict = None) -> str:
    doc_id = _id(title)
    meta   = {"title": title, **(extra_meta or {})}
    jd_col().upsert(
        ids=[doc_id],
        documents=[text[:8000]],
        metadatas=[meta],
    )
    return doc_id


# ── search ──────────────────────────────────────────────────────────────────
def search_resumes_for_jd(jd_text: str, top_k: int = 50) -> list:
    col = resume_col()
    n   = col.count()
    if n == 0:
        return []
    results = col.query(query_texts=[jd_text[:2000]], n_results=min(top_k, n))
    return [
        {
            "text":     results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "score":    round((1 - results["distances"][0][i]) * 100, 1),
        }
        for i in range(len(results["documents"][0]))
    ]


def search_jds_for_candidate(cand_text: str, top_k: int = 5) -> list:
    col = jd_col()
    n   = col.count()
    if n == 0:
        return []
    results = col.query(query_texts=[cand_text[:2000]], n_results=min(top_k, n))
    return [
        {
            "text":     results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "score":    round((1 - results["distances"][0][i]) * 100, 1),
        }
        for i in range(len(results["documents"][0]))
    ]


# ── get all ─────────────────────────────────────────────────────────────────
def get_all_resumes() -> list:
    """FIX 4 + FIX 6 — returns every stored resume with its id for deletion."""
    col = resume_col()
    if col.count() == 0:
        return []
    r = col.get(include=["documents", "metadatas"])
    return [
        {"id": r["ids"][i], "text": r["documents"][i], "metadata": r["metadatas"][i]}
        for i in range(len(r["ids"]))
    ]


def get_all_jds() -> list:
    col = jd_col()
    if col.count() == 0:
        return []
    r = col.get(include=["documents", "metadatas"])
    return [
        {"id": r["ids"][i], "text": r["documents"][i], "metadata": r["metadatas"][i]}
        for i in range(len(r["ids"]))
    ]


# ── delete ──────────────────────────────────────────────────────────────────
def delete_resume(doc_id: str):
    """FIX 6 — remove a single resume from the knowledge base."""
    resume_col().delete(ids=[doc_id])


def delete_jd(doc_id: str):
    jd_col().delete(ids=[doc_id])


# ── counts ──────────────────────────────────────────────────────────────────
def resume_count() -> int:
    return resume_col().count()


def jd_count() -> int:
    return jd_col().count()
