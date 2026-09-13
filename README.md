# 🎓 MBA Copilot

AI tutor grounded in your MBA course material, with a separate **Ask GPT** mode and a secured knowledge-management portal.

## Architecture

GitHub → Render Web Service → Render Postgres + pgvector → OpenAI

- 📚 **Ask MBA Copilot** — course-grounded answers
- 🤖 **Ask GPT** — general GPT answers
- 📑 Clickable source references
- 🧠 Concept-aware retrieval and relevance filtering
- 🔐 Individual administrator authentication
- 🗂️ Admin document management: upload, replace, re-index and delete
- 🗄️ Hosted PostgreSQL knowledge library

## Admin access

Set `ADMIN_USERS` in Render Environment Variables as a JSON object mapping authorized email addresses to private access codes. Example format:

```text
{"admin1@example.com":"private-code-1","admin2@example.com":"private-code-2"}
```

Never commit real access codes to GitHub. The browser only receives an authenticated session; the configured admin list remains server-side.

## Deploy

Use the Render Blueprint in `render.yaml` or create a Render Web Service from this repository. Render should run `python bootstrap.py`; this installs the secure admin-management routes before starting the server.

Required environment variables:

- `OPENAI_API_KEY` — add in Render Environment Variables; never commit it.
- `ADMIN_USERS` — JSON map of authorized administrator emails to private access codes.
- `MBA_COPILOT_MODEL` — defaults to `gpt-4.1-mini`.
- `DATABASE_URL` — populated by the Render Blueprint from managed Postgres.

## Admin workflow

**Admin sign-in → Select subject → Upload → Extract/index → Review library → Re-index / Replace / Delete**

Students can use the MBA Library and ask questions, but database-management controls require an authorized admin session.

## Local run

```bash
pip install -r requirements.txt
python bootstrap.py
```
