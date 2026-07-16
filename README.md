# RAG local (Docker Desktop)

Stack: Streamlit (frontend) + FastAPI/LangChain (backend) + Ollama (LLM y embeddings) + Qdrant (base vectorial). Corre 100% en tu equipo, sin costo ni llamadas a Azure.

## Requisitos

- Docker Desktop instalado y corriendo.
- ~6-8 GB de RAM asignados a Docker Desktop (Settings > Resources) para que Ollama corra cómodo.

## Levantar el stack

```bash
cd rag-local
docker compose up -d --build
```

## Descargar los modelos (solo la primera vez)

Ollama arranca sin modelos descargados. Con los contenedores ya corriendo:

```bash
docker compose exec ollama ollama pull phi3.5
docker compose exec ollama ollama pull nomic-embed-text
```

`phi3.5` pesa ~2.2 GB. Si tu equipo tiene poca RAM, usa un modelo más chico cambiando `OLLAMA_LLM_MODEL` en `.env` (copia `.env.example` a `.env`) por `llama3.2:1b`, por ejemplo, y luego `docker compose exec ollama ollama pull llama3.2:1b`.

## Usar la app

Abre http://localhost:8501

1. Pestaña **Subir documentos**: sube uno o varios PDF/DOCX/TXT/MD y presiona "Procesar documentos".
2. Pestaña **Preguntar**: escribe tu pregunta en el chat. La respuesta viene acompañada de las fuentes (documento + fragmento) usadas para generarla.

## Endpoints del backend (por si quieres probarlos directo)

- `GET  http://localhost:8000/health`
- `POST http://localhost:8000/ingest` (multipart, campo `file`)
- `POST http://localhost:8000/ask` (`{"question": "..."}`)

## Apagar

```bash
docker compose down          # detiene los contenedores, conserva los datos
docker compose down -v       # además borra los volúmenes (modelos y vectores)
```

## Estructura

```
rag-local/
  docker-compose.yml
  .env.example
  docs/              # documentos originales subidos (volumen)
  backend/
    Dockerfile
    requirements.txt
    app/
      main.py         # endpoints FastAPI
      rag.py          # ingesta + respuesta (RAG)
      loaders.py       # extracción de texto por formato
      config.py         # variables de entorno
  frontend/
    Dockerfile
    requirements.txt
    app.py            # UI Streamlit
```

## Siguiente paso

Esta misma estructura (4 contenedores) es la base para desplegar en Azure Container Apps reutilizando las mismas imágenes — solo cambia dónde corren y dónde se guardan los documentos (Blob Storage en vez del volumen `./docs`).
