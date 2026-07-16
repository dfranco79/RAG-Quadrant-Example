"""Logica de ingesta, respuesta (RAG) y resumen usando Ollama + Qdrant."""
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from . import config
from .loaders import load_text

_embeddings = OllamaEmbeddings(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_EMBED_MODEL)
_llm = ChatOllama(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_LLM_MODEL, temperature=0.1)
_client = QdrantClient(url=config.QDRANT_URL)

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=config.CHUNK_SIZE,
    chunk_overlap=config.CHUNK_OVERLAP,
)

# Tamano maximo (en caracteres) de cada bloque que se le manda al LLM para
# resumir. Documentos grandes se parten en varios bloques y se resumen en
# dos pasadas (mapa -> combinacion), para no exceder la ventana de contexto.
_SUMMARY_GROUP_CHARS = 6000


def _collection_exists() -> bool:
    names = [c.name for c in _client.get_collections().collections]
    return config.QDRANT_COLLECTION in names


def _ensure_collection(vector_size: int) -> None:
    if not _collection_exists():
        _client.create_collection(
            collection_name=config.QDRANT_COLLECTION,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )


def ingest_file(path: Path, filename: str) -> int:
    text = load_text(path)
    if not text.strip():
        return 0

    chunks = _splitter.split_text(text)
    if not chunks:
        return 0

    vectors = _embeddings.embed_documents(chunks)
    _ensure_collection(vector_size=len(vectors[0]))

    points = [
        qmodels.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={"text": chunk, "source": filename, "chunk_index": i},
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]
    _client.upsert(collection_name=config.QDRANT_COLLECTION, points=points)
    return len(points)


def list_sources() -> List[str]:
    """Nombres de archivo distintos que hay indexados, para poblar el selector."""
    if not _collection_exists():
        return []

    sources = set()
    next_offset = None
    while True:
        points, next_offset = _client.scroll(
            collection_name=config.QDRANT_COLLECTION,
            with_payload=True,
            with_vectors=False,
            limit=200,
            offset=next_offset,
        )
        for p in points:
            sources.add(p.payload["source"])
        if next_offset is None:
            break
    return sorted(sources)


def _source_filter(source: str) -> qmodels.Filter:
    return qmodels.Filter(
        must=[qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=source))]
    )


def _fetch_all_chunks(source: str) -> List[str]:
    """Trae TODOS los fragmentos de un documento (no solo los top-k), en orden."""
    points_acc = []
    next_offset = None
    while True:
        points, next_offset = _client.scroll(
            collection_name=config.QDRANT_COLLECTION,
            scroll_filter=_source_filter(source),
            with_payload=True,
            with_vectors=False,
            limit=200,
            offset=next_offset,
        )
        points_acc.extend(points)
        if next_offset is None:
            break

    points_acc.sort(key=lambda p: p.payload.get("chunk_index", 0))
    return [p.payload["text"] for p in points_acc]


def answer_question(
    question: str, k: Optional[int] = None, source: Optional[str] = None
) -> Dict[str, Any]:
    k = k or config.TOP_K

    if not _collection_exists():
        return {
            "answer": "Todavia no hay documentos ingeridos. Sube al menos uno antes de preguntar.",
            "sources": [],
        }

    query_vector = _embeddings.embed_query(question)
    response = _client.query_points(
        collection_name=config.QDRANT_COLLECTION,
        query=query_vector,
        query_filter=_source_filter(source) if source else None,
        limit=k,
    )
    results = response.points

    if not results:
        return {"answer": "No encontre informacion relevante en los documentos cargados.", "sources": []}

    context = "\n\n---\n\n".join(r.payload["text"] for r in results)
    sources = [
        {
            "source": r.payload["source"],
            "score": round(r.score, 3),
            "snippet": r.payload["text"][:200],
        }
        for r in results
    ]

    prompt = (
        "Eres un asistente que responde preguntas usando SOLO el contexto entregado. "
        "Si la respuesta no esta en el contexto, dilo explicitamente en vez de inventar.\n\n"
        f"Contexto:\n{context}\n\n"
        f"Pregunta: {question}\n\n"
        "Respuesta:"
    )

    response = _llm.invoke(prompt)
    answer = response.content if hasattr(response, "content") else str(response)

    return {"answer": answer, "sources": sources}


def _group_chunks(chunks: List[str], group_chars: int) -> List[str]:
    groups: List[str] = []
    current = ""
    for chunk in chunks:
        if current and len(current) + len(chunk) > group_chars:
            groups.append(current)
            current = chunk
        else:
            current = f"{current}\n\n{chunk}" if current else chunk
    if current:
        groups.append(current)
    return groups


def summarize_document(source: str) -> Dict[str, Any]:
    """Resume un documento completo (todos sus fragmentos, no solo los mas
    similares a una pregunta). Si el documento es grande, resume por bloques
    y despues combina esos resumenes parciales en uno final."""
    chunks = _fetch_all_chunks(source)
    if not chunks:
        return {"summary": f"No encontre el documento '{source}' en la base.", "chunks_used": 0}

    groups = _group_chunks(chunks, _SUMMARY_GROUP_CHARS)

    if len(groups) == 1:
        prompt = (
            "Resume el siguiente documento en espanol, de forma clara y "
            "concisa (6-8 oraciones). No inventes informacion que no este "
            f"en el texto:\n\n{groups[0]}"
        )
        summary = _llm.invoke(prompt).content
        return {"summary": summary, "chunks_used": len(chunks)}

    partial_summaries = []
    for group in groups:
        prompt = (
            "Resume brevemente esta seccion de un documento mas grande "
            f"(3-4 oraciones), en espanol:\n\n{group}"
        )
        partial_summaries.append(_llm.invoke(prompt).content)

    combined = "\n\n".join(partial_summaries)
    final_prompt = (
        "A continuacion hay resumenes parciales de distintas secciones de "
        "un mismo documento. Combinalos en un resumen final coherente, en "
        f"espanol, de no mas de 10 oraciones:\n\n{combined}"
    )
    final_summary = _llm.invoke(final_prompt).content

    return {"summary": final_summary, "chunks_used": len(chunks)}
