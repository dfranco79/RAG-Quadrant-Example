import os

import requests
import streamlit as st


def _get_backend_url() -> str:
    """En Docker Compose viene por variable de entorno. En Streamlit
    Cloud se define como Secret (Settings > Secrets) y llega por
    st.secrets. Se prueba st.secrets primero y se cae a env var."""
    try:
        return st.secrets["BACKEND_URL"]
    except Exception:
        return os.getenv("BACKEND_URL", "http://backend:8000")


BACKEND_URL = _get_backend_url()

st.set_page_config(page_title="RAG local", page_icon="📄", layout="wide")
st.title("📄 Preguntas sobre tus documentos")


def _fetch_sources():
    try:
        resp = requests.get(f"{BACKEND_URL}/documents", timeout=30)
        if resp.ok:
            return resp.json().get("sources", [])
    except requests.RequestException:
        pass
    return []


tab_ingest, tab_ask, tab_summary = st.tabs(["Subir documentos", "Preguntar", "Resumir"])

with tab_ingest:
    st.subheader("Subir documentos")
    st.caption("Formatos soportados: PDF, DOCX, TXT, MD")

    files = st.file_uploader(
        "Selecciona uno o mas archivos",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
    )

    if st.button("Procesar documentos", disabled=not files):
        for file in files:
            with st.spinner(f"Procesando {file.name}..."):
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/ingest",
                        files={"file": (file.name, file.getvalue())},
                        timeout=6000000,
                    )
                except requests.RequestException as exc:
                    st.error(f"{file.name}: no se pudo contactar al backend ({exc})")
                    continue

            if resp.ok:
                data = resp.json()
                st.success(f"{file.name}: {data['chunks']} fragmentos indexados")
            else:
                st.error(f"{file.name}: {resp.text}")

with tab_ask:
    st.subheader("Preguntar")

    sources = _fetch_sources()
    options = ["Todos los documentos"] + sources
    selected = st.selectbox("Buscar en", options, key="ask_source")
    source_filter = None if selected == "Todos los documentos" else selected

    if not sources:
        st.info("Todavia no hay documentos indexados. Sube uno en la pestaña anterior.")

    if "history" not in st.session_state:
        st.session_state.history = []

    for turn in st.session_state.history:
        with st.chat_message(turn["role"]):
            st.write(turn["content"])

    question = st.chat_input("Escribe tu pregunta...")
    if question:
        st.session_state.history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.write(question)

        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/ask",
                        json={"question": question, "source": source_filter},
                        timeout=6000000,
                    )
                except requests.RequestException as exc:
                    resp = None
                    answer_text = f"No se pudo contactar al backend ({exc})"
                    st.error(answer_text)

            if resp is not None:
                if resp.ok:
                    data = resp.json()
                    answer_text = data["answer"]
                    st.write(answer_text)
                    if data.get("sources"):
                        with st.expander("Fuentes"):
                            for s in data["sources"]:
                                st.caption(
                                    f"{s['source']} (score {s['score']}): {s['snippet']}..."
                                )
                else:
                    answer_text = f"Error: {resp.text}"
                    st.error(answer_text)

        st.session_state.history.append({"role": "assistant", "content": answer_text})

with tab_summary:
    st.subheader("Resumir un documento completo")
    st.caption(
        "A diferencia de 'Preguntar', esto usa TODOS los fragmentos del "
        "documento elegido, no solo los mas parecidos a una pregunta — "
        "sirve para pedir un resumen general."
    )

    sources = _fetch_sources()
    if not sources:
        st.info("Todavia no hay documentos indexados. Sube uno en la primera pestaña.")
    else:
        doc_to_summarize = st.selectbox("Documento", sources, key="summary_source")
        if st.button("Generar resumen"):
            with st.spinner(f"Resumiendo {doc_to_summarize}..."):
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/summarize",
                        json={"source": doc_to_summarize},
                        timeout=600,
                    )
                except requests.RequestException as exc:
                    resp = None
                    st.error(f"No se pudo contactar al backend ({exc})")

            if resp is not None:
                if resp.ok:
                    data = resp.json()
                    st.write(data["summary"])
                    st.caption(f"Basado en {data['chunks_used']} fragmentos del documento.")
                else:
                    st.error(resp.text)
