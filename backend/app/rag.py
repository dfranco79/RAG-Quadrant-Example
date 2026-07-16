"""Logica de ingesta y respuesta (RAG) usando Ollama + Qdrant."""
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

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


def answer_question(question: str, k: Optional[int] = None) -> Dict[str, Any]:
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
