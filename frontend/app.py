import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

st.set_page_config(page_title="RAG local", page_icon="📄", layout="wide")
st.title("📄 Preguntas sobre tus documentos")

tab_ingest, tab_ask = st.tabs(["Subir documentos", "Preguntar"])

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
                        timeout=300,
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
                        f"{BACKEND_URL}/ask", json={"question": question}, timeout=300
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
