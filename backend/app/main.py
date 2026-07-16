import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, rag

app = FastAPI(title="RAG local API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Path(config.DOCS_DIR).mkdir(parents=True, exist_ok=True)

ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


class AskRequest(BaseModel):
    question: str
    k: Optional[int] = None
    source: Optional[str] = None


class SummarizeRequest(BaseModel):
    source: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/documents")
def documents():
    return {"sources": rag.list_sources()}


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Formato no soportado: {suffix}")

    docs_dir = Path(config.DOCS_DIR)
    # Se guarda primero con nombre temporal. Solo se renombra al nombre
    # final si la indexacion termina bien, para que docs/ nunca tenga un
    # archivo "a medias" si algo falla en el camino.
    tmp_path = docs_dir / f".tmp_{file.filename}"
    final_path = docs_dir / file.filename

    with tmp_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        n_chunks = rag.ingest_file(tmp_path, file.filename)
    except Exception as exc:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Error procesando el archivo: {exc}") from exc

    if n_chunks == 0:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            422,
            f"'{file.filename}' no se pudo indexar: no se extrajo texto "
            "(¿es un PDF escaneado o una imagen sin capa de texto?). "
            "No se guardo.",
        )

    tmp_path.replace(final_path)
    return {"status": "ok", "filename": file.filename, "chunks": n_chunks}


@app.post("/ask")
def ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(400, "La pregunta no puede estar vacia")
    try:
        return rag.answer_question(req.question, k=req.k, source=req.source)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Error respondiendo la pregunta: {exc}") from exc


@app.post("/summarize")
def summarize(req: SummarizeRequest):
    try:
        return rag.summarize_document(req.source)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Error generando el resumen: {exc}") from exc
