import os
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import re
import requests
import chromadb
from models import MuseumDoc

CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "museum_species")

OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150):
    text = (text or "").strip()
    if not text:
        return []
    text = re.sub(r"\n{3,}", "\n\n", text)
    chunks = []
    i = 0
    while i < len(text):
        j = min(len(text), i + chunk_size)
        chunks.append(text[i:j])
        i = max(j - overlap, j)
        if i >= len(text):
            break
    return [c.strip() for c in chunks if c.strip()]

def ollama_embed(texts: list[str]) -> list[list[float]]:
    r = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "input": texts},
        timeout=90
    )
    r.raise_for_status()
    return r.json()["embeddings"]

class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)

    def reindex_species(self, species_id: str, museo_info: str):
        # borrar embeddings anteriores de esa especie
        existing = self.collection.get(where={"species_id": species_id})
        if existing and existing.get("ids"):
            self.collection.delete(ids=existing["ids"])

        docs_to_index: list[tuple[str, dict]] = []

        if (museo_info or "").strip():
            docs_to_index.append((museo_info.strip(), {"source": "museo_text"}))

        museum_docs = MuseumDoc.query.filter_by(species_id=species_id).all()
        for d in museum_docs:
            if (d.extracted_text or "").strip():
                docs_to_index.append((
                    d.extracted_text.strip(),
                    {"source": "museo_doc", "doc_id": d.id, "original_name": d.original_name, "file_type": d.file_type}
                ))

        all_chunks = []
        all_meta = []
        for raw_text, meta in docs_to_index:
            for i, ch in enumerate(chunk_text(raw_text)):
                all_chunks.append(ch)
                all_meta.append({"species_id": species_id, "chunk": i, **meta})

        if not all_chunks:
            return

        embeds = ollama_embed(all_chunks)
        ids = [f"{species_id}::chunk::{i}" for i in range(len(all_chunks))]

        self.collection.upsert(
            ids=ids,
            documents=all_chunks,
            embeddings=embeds,
            metadatas=all_meta
        )

    def query_species(self, species_id: str, question: str, k: int = 4) -> list[dict]:
        q_embed = ollama_embed([question])[0]
        res = self.collection.query(
            query_embeddings=[q_embed],
            n_results=k,
            where={"species_id": species_id},
            include=["documents", "metadatas", "distances"],
        )
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out = []
        for doc, meta, dist in zip(docs, metas, dists):
            out.append({"text": doc, "meta": meta, "distance": dist})
        return out