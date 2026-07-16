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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, f"Formato no soportado: {suffix}")

    dest = Path(config.DOCS_DIR) / file.filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        n_chunks = rag.ingest_file(dest, file.filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Error procesando el archivo: {exc}") from exc

    return {"status": "ok", "filename": file.filename, "chunks": n_chunks}


@app.post("/ask")
def ask(req: AskRequest):
    if not req.question.strip():
        raise HTTPException(400, "La pregunta no puede estar vacia")
    try:
        return rag.answer_question(req.question, k=req.k)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Error respondiendo la pregunta: {exc}") from exc
