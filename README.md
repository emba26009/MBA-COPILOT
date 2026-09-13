# MBA Copilot

AI tutor for an MBA course library.

## Two answer modes
- 📚 **Ask MBA Copilot** — grounded in uploaded course material, with source references.
- 🤖 **Ask GPT** — general-purpose GPT answer, not restricted to the course library.

## Current focus
V8.4 baseline with clickable references and separate Ask GPT mode. The next iteration will strengthen relevance filtering and production RAG.

## Security
Course files and secrets should not be committed to this public repository. Configure `OPENAI_API_KEY` as a hosting-platform environment variable.

## Run locally
`pip install -r requirements.txt`

`python app.py`

The server uses the hosting platform's `PORT` and binds to `0.0.0.0`.
