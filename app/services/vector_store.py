# Vector store — pgvector operations for LinkedIn and Resume candidate embeddings.
# Stores embeddings at ingest time, retrieves similar candidates at query time.
# Falls back gracefully if pgvector extension is not enabled on Neon.

from sqlalchemy.orm import Session
from sqlalchemy import text


def ensure_tables(db: Session) -> None:
    """Creates embedding tables if they don't exist. Safe to call repeatedly."""
    try:
        db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS candidate_embeddings (
                id SERIAL PRIMARY KEY,
                candidate_type VARCHAR(20) NOT NULL,
                candidate_id INTEGER NOT NULL,
                embedding vector(768),
                UNIQUE(candidate_type, candidate_id)
            )
        """))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS jd_embeddings (
                id SERIAL PRIMARY KEY,
                jd_id INTEGER NOT NULL UNIQUE,
                embedding vector(768)
            )
        """))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[VectorStore] Table setup skipped: {e}")


def upsert_candidate_embedding(
    db: Session,
    candidate_type: str,
    candidate_id: int,
    embedding: list[float],
) -> None:
    """Stores or updates a candidate embedding. candidate_type: 'linkedin' or 'resume'."""
    try:
        vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
        db.execute(text("""
            INSERT INTO candidate_embeddings (candidate_type, candidate_id, embedding)
            VALUES (:ctype, :cid, CAST(:emb AS vector))
            ON CONFLICT (candidate_type, candidate_id)
            DO UPDATE SET embedding = EXCLUDED.embedding
        """), {"ctype": candidate_type, "cid": candidate_id, "emb": vector_str})
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[VectorStore] Failed to upsert embedding: {e}")


def upsert_jd_embedding(db: Session, jd_id: int, embedding: list[float]) -> None:
    """Stores or updates a JD embedding."""
    try:
        vector_str = "[" + ",".join(str(x) for x in embedding) + "]"
        db.execute(text("""
            INSERT INTO jd_embeddings (jd_id, embedding)
            VALUES (:jd_id, CAST(:emb AS vector))
            ON CONFLICT (jd_id)
            DO UPDATE SET embedding = EXCLUDED.embedding
        """), {"jd_id": jd_id, "emb": vector_str})
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[VectorStore] Failed to upsert JD embedding: {e}")


def find_similar_candidates(
    db: Session,
    jd_embedding: list[float],
    top_k: int = 20,
) -> list[tuple[str, int, float]]:
    """
    Returns top-K most similar candidates to the JD.
    Result: list of (candidate_type, candidate_id, similarity_score).
    Returns [] if pgvector unavailable.
    """
    try:
        vector_str = "[" + ",".join(str(x) for x in jd_embedding) + "]"
        rows = db.execute(text("""
            SELECT candidate_type, candidate_id,
                   1 - (embedding <=> CAST(:emb AS vector)) AS similarity
            FROM candidate_embeddings
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT :k
        """), {"emb": vector_str, "k": top_k}).fetchall()
        return [(r[0], r[1], float(r[2])) for r in rows]
    except Exception:
        return []


def get_jd_embedding(db: Session, jd_id: int) -> list[float] | None:
    """Retrieves a cached JD embedding from DB."""
    try:
        row = db.execute(
            text("SELECT embedding FROM jd_embeddings WHERE jd_id = :jd_id"),
            {"jd_id": jd_id}
        ).fetchone()
        if row and row[0]:
            return [float(x) for x in row[0]]
    except Exception:
        pass
    return None