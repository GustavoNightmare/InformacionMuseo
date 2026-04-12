import os
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import re

import chromadb
import requests

from models import MuseumDoc, Species

CHROMA_PATH = os.getenv("CHROMA_PATH", "chroma_db")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "museum_species")

OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

SPECIMEN_CONTENT_TERMS = (
    "espécimen", "especimen", "ejemplar", "pieza", "exhibido", "expuesto",
    "museo", "colección", "coleccion", "vitrina", "procedencia", "origen",
    "hallado", "hallada", "encontrado", "encontrada", "colectado", "colectada",
    "recolectado", "recolectada", "capturado", "capturada", "donado", "donada",
    "registro", "inventario", "localidad", "sitio", "fecha", "sala"
)


def chunk_text(text: str, chunk_size: int = 850, overlap: int = 160) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(text_len, start + chunk_size)

        if end < text_len:
            search_from = min(text_len, start + max(250, chunk_size // 2))
            cut_candidates = [
                text.rfind("\n\n", search_from, end),
                text.rfind(". ", search_from, end),
                text.rfind("; ", search_from, end),
                text.rfind(": ", search_from, end),
            ]
            best_cut = max(cut_candidates)
            if best_cut > start:
                end = best_cut + (2 if text[best_cut:best_cut + 2] in {"\n\n", ". ", "; ", ": "} else 0)

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break

        next_start = max(0, end - overlap)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def ollama_embed(texts: list[str]) -> list[list[float]]:
    r = requests.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "input": texts},
        timeout=90,
    )
    r.raise_for_status()
    return r.json()["embeddings"]


class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)

    def reindex_species(self, species_id: str, museo_info: str):
        existing = self.collection.get(where={"species_id": species_id})
        if existing and existing.get("ids"):
            self.collection.delete(ids=existing["ids"])

        docs_to_index: list[tuple[str, dict]] = []
        species = Species.query.get(species_id)
        species_label = None
        if species:
            names = [n for n in [species.nombre_comun, species.nombre_cientifico] if (n or "").strip()]
            species_label = " / ".join(names)

        if (museo_info or "").strip():
            enriched = (museo_info or "").strip()
            if species_label:
                enriched = (
                    "Fuente: nota curatorial del museo.\n"
                    f"Animal actual: {species_label}.\n"
                    "Este texto puede contener datos del ejemplar expuesto, su procedencia, sala, historia local o mediación.\n\n"
                    f"{enriched}"
                )
            docs_to_index.append((enriched, {"source": "museo_text", "source_label": "nota curatorial"}))

        museum_docs = MuseumDoc.query.filter_by(species_id=species_id).all()
        for d in museum_docs:
            if (d.extracted_text or "").strip():
                enriched = d.extracted_text.strip()
                if species_label:
                    enriched = (
                        "Fuente: documento del museo.\n"
                        f"Animal actual: {species_label}.\n"
                        f"Documento: {d.original_name}.\n\n"
                        f"{enriched}"
                    )
                docs_to_index.append((
                    enriched,
                    {
                        "source": "museo_doc",
                        "source_label": d.original_name,
                        "doc_id": d.id,
                        "original_name": d.original_name,
                        "file_type": d.file_type,
                    },
                ))

        all_chunks = []
        all_meta = []
        global_chunk_index = 0
        for raw_text, meta in docs_to_index:
            for local_chunk_index, ch in enumerate(chunk_text(raw_text)):
                all_chunks.append(ch)
                all_meta.append({
                    "species_id": species_id,
                    "chunk": local_chunk_index,
                    "global_chunk": global_chunk_index,
                    **meta,
                })
                global_chunk_index += 1

        if not all_chunks:
            return

        embeds = ollama_embed(all_chunks)
        ids = [f"{species_id}::chunk::{i}" for i in range(len(all_chunks))]

        self.collection.upsert(
            ids=ids,
            documents=all_chunks,
            embeddings=embeds,
            metadatas=all_meta,
        )

    @staticmethod
    def _build_query_variants(question: str, question_scope: str) -> list[str]:
        question = (question or "").strip()
        variants = [question]

        if question_scope == "specimen":
            variants.append(
                "dato específico del ejemplar expuesto en el museo, procedencia, hallazgo, colección, registro: "
                + question
            )
            variants.append(
                "espécimen exhibido, pieza del museo, localidad exacta, origen del ejemplar: " + question
            )
        elif question_scope == "general":
            variants.append("información general de la especie, biología y ecología: " + question)

        deduped: list[str] = []
        seen = set()
        for item in variants:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped

    @staticmethod
    def _score_chunk(question: str, question_scope: str, doc: str, meta: dict, distance: float) -> float:
        q = (question or "").lower()
        d = (doc or "").lower()
        score = -(distance or 0.0)

        if meta.get("source") == "museo_text":
            score += 0.35
        if meta.get("source") == "museo_doc":
            score += 0.10

        query_terms = [token for token in re.findall(r"\w+", q) if len(token) >= 4]
        score += min(0.30, 0.03 * sum(1 for token in query_terms if token in d))

        specimen_hits = sum(1 for term in SPECIMEN_CONTENT_TERMS if term in d)
        if question_scope == "specimen":
            score += min(0.60, specimen_hits * 0.08)
        elif question_scope == "general" and specimen_hits:
            score -= min(0.20, specimen_hits * 0.03)

        return score

    def query_species(
        self,
        species_id: str,
        question: str,
        k: int = 4,
        question_scope: str = "mixed",
    ) -> list[dict]:
        query_variants = self._build_query_variants(question, question_scope)
        query_embeddings = ollama_embed(query_variants)
        raw_k = max(k * 2, 8)

        res = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=raw_k,
            where={"species_id": species_id},
            include=["documents", "metadatas", "distances"],
        )

        ids_rows = res.get("ids") or []
        docs_rows = res.get("documents") or []
        metas_rows = res.get("metadatas") or []
        dists_rows = res.get("distances") or []

        by_id: dict[str, dict] = {}
        for ids_row, docs_row, metas_row, dists_row in zip(ids_rows, docs_rows, metas_rows, dists_rows):
            for doc_id, doc, meta, dist in zip(ids_row, docs_row, metas_row, dists_row):
                item = {
                    "id": doc_id,
                    "text": doc,
                    "meta": meta,
                    "distance": dist,
                    "score": self._score_chunk(question, question_scope, doc, meta or {}, dist),
                }
                previous = by_id.get(doc_id)
                if previous is None or item["score"] > previous["score"]:
                    by_id[doc_id] = item

        ranked = sorted(by_id.values(), key=lambda item: item["score"], reverse=True)
        return ranked[:k]
