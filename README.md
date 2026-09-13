# 🎓 MBA Copilot

AI tutor grounded in your MBA course material, with a separate **Ask GPT** mode.

## Current architecture

GitHub → Render Web Service → Render Postgres + pgvector → OpenAI

- 📚 **Ask MBA Copilot** — course-grounded answers
- 🤖 **Ask GPT** — general GPT answers
- 📑 Clickable source references
- 🧠 Concept-aware retrieval and relevance filtering
- 🗄️ Hosted PostgreSQL knowledge-library foundation

## Deploy

Use the Render Blueprint in `render.yaml` or create a Render Web Service from this repository. Render supports GitHub-connected web services and automatic redeploys on pushes. Keep secrets in Render Environment Variables rather than Git.

## Required environment variables

- `OPENAI_API_KEY` — add in Render Environment Variables; never commit it.
- `MBA_COPILOT_MODEL` — defaults to `gpt-4.1-mini`.
- `DATABASE_URL` — populated by the Render Blueprint from the managed Postgres database.

## Next ingestion step

The database foundation is ready for the real MBA library. The next ingestion layer will upload PDFs/PPT/DOCX/XLSX/ZIP case studies, extract passages and page/slide/sheet locators, generate embeddings, and write them into Postgres/pgvector. The answer engine will then retrieve semantically relevant evidence before GPT synthesis.

## Local run

```bash
pip install -r requirements.txt
python app.py
```
