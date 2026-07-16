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

## Preguntar sobre un documento especifico o resumir uno completo

- **Pestaña "Preguntar"**: el selector "Buscar en" te deja elegir un
  documento puntual en vez de buscar entre todos los que subiste. Si
  subiste varios archivos, elegir el correcto evita que la respuesta se
  mezcle con contenido de otro documento (por ejemplo, que una pregunta
  sobre un PDF nuevo te responda con datos de tu CV).
- **Pestaña "Resumir"**: para pedir un resumen general de un documento
  completo. Es distinto a "Preguntar": ahi se usan TODOS los fragmentos del
  documento (no solo los 3-4 mas parecidos a la pregunta), asi que sirve
  para resumenes de verdad en vez de respuestas puntuales.
- Si al subir un archivo te aparece un error diciendo que no se pudo
  extraer texto, revisa si es un PDF escaneado (imagen sin capa de texto).
  `pypdf` no hace OCR — para esos casos habria que agregar una libreria de
  OCR aparte.

## Publicar el frontend en Streamlit Cloud (con tunel)

Streamlit Community Cloud solo corre `frontend/app.py` instalando
`frontend/requirements.txt` — no puede levantar Docker, Ollama ni Qdrant.
Para que el frontend publicado pueda hablar con tu backend local, exponlo
a internet con un tunel de Cloudflare (no requiere cuenta ni tarjeta):

### 1. Levanta tu stack local

```bash
docker compose up -d
```

Confirma que responde: `http://localhost:8000/health`

### 2. Instala cloudflared y abre el tunel

Windows (PowerShell o Git Bash):
```bash
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:8000
```

Te va a imprimir una URL publica del tipo:
`https://palabras-al-azar.trycloudflare.com`

Pruebala en el navegador agregando `/health` al final — debe responder
`{"status":"ok"}`. **Dejalo corriendo**: si cierras esa terminal, el tunel
se cae y el frontend publicado deja de poder responder preguntas. Cada vez
que reinicies `cloudflared` la URL cambia, hay que actualizar el Secret
del paso 4.

### 3. Conecta el repo en Streamlit Cloud

1. Entra a [share.streamlit.io](https://share.streamlit.io) con tu cuenta
   de GitHub.
2. "New app" > selecciona tu repo, rama `main`.
3. Main file path: `frontend/app.py`
   (Streamlit detecta `frontend/requirements.txt` solo, por estar en la
   misma carpeta que el script).

### 4. Configura el Secret con la URL del tunel

En "Advanced settings" antes de deployar (o despues, en Settings > Secrets
de la app ya creada), agrega:

```toml
BACKEND_URL = "https://palabras-al-azar.trycloudflare.com"
```

### 5. Deploy

Dale a "Deploy". Cuando el tunel siga activo en tu PC, el frontend
publicado va a poder subir documentos y responder preguntas contra tu
Ollama/Qdrant local.

Esto sirve para probar y compartir una demo puntual. Para algo que se
pueda usar sin depender de que tu PC este prendida, el siguiente paso es
mover el backend a Azure Container Apps (ver el documento de arquitectura).

## Siguiente paso

Esta misma estructura (4 contenedores) es la base para desplegar en Azure Container Apps reutilizando las mismas imágenes — solo cambia dónde corren y dónde se guardan los documentos (Blob Storage en vez del volumen `./docs`).
