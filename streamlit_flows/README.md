# Streamlit Flow Lab

This folder is a small manual test lab for backend flows before wiring them into the React UI.

Run from the repository root:

```bash
streamlit run streamlit_flows/Home.py
```

Start FastAPI separately before using the flow pages. The Streamlit pages call FastAPI through `flow_client.py`; they no longer call backend services directly.

Each file in `pages/` should represent one product flow or one step inside a larger flow.
