# Notes to MCQs

Upload study notes (PDF or TXT) or paste text, and get multiple-choice questions. Each question is rated for difficulty and quality with explainable fuzzy-logic rules. You can review the questions, take the quiz in the browser, and export the results.

The interface is plain HTML, CSS and JavaScript, served by a small Flask server. It replaces the Streamlit app.

## Run it

```bash
python -m venv venv
venv\Scripts\activate          # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
# put your key in .env as GOOGLE_API_KEY=...
python server.py
```

Open http://127.0.0.1:8000.

No API key yet? Set `DEMO_MODE=1` in `.env` to try the interface. Demo mode builds simple fill-in-the-blank questions with text rules. They are not AI-written, and the interface says so.

## Project layout

| File | What it does |
| --- | --- |
| `server.py` | Flask app: serves `static/` and exposes `/api/config` and `/api/generate` |
| `pipeline.py` | One function, `generate_quiz`, that runs retrieval, generation and fuzzy scoring |
| `rag_engine.py` | Corrective retrieval over the notes, with optional web fallback |
| `llm_service.py` | Gemini call, JSON parsing and error messages |
| `fuzzy_logic.py` | Fuzzy difficulty and quality assessment |
| `schemas.py` | Pydantic models for questions |
| `text_extraction.py` | PDF and TXT reading |
| `demo_mode.py` | Offline questions for trying the UI |
| `static/` | `index.html`, `styles.css`, `app.js` |

## API

`POST /api/generate` (multipart form)

| Field | Meaning |
| --- | --- |
| `file` or `text` | The notes: an uploaded .pdf/.txt, or pasted text |
| `num_questions` | 1 to 10 (default 5) |
| `topic` | Optional focus topic |
| `allow_web` | `1` or `0`: allow web search when notes fall short |
| `max_web_results` | 1 to 5 |

Returns `{ "questions": [...], "meta": {...} }`. Errors return `{ "error": "<code>", "message": "<what to do>" }` with a matching HTTP status.

## What changed from the Streamlit version

- **Gemini replies are parsed reliably.** The old code failed whenever the model wrapped its JSON in a code fence. Now the JSON is extracted, valid questions are kept even if one is malformed, duplicates are dropped, and one retry is made.
- **Answers are normalised.** `"B"`, `"A. text"` and case differences in `correct_answer` map to the exact option.
- **Options are shuffled** so the correct answer isn't always in the same slot.
- **Questions cover the whole notes.** Retrieval picks passages with maximal marginal relevance across the document instead of the six that best match one generic sentence. The old version could only ever see about 5,000 characters.
- **Optional focus topic.** Retrieval retries with a broader query if the topic isn't found, and tells you when the notes don't cover it.
- **Web fallback triggers on real weakness**, and searches with your topic or the notes' key terms rather than the instruction sentence.
- **Fuzzy difficulty is a real rule base** over question length, reasoning cues and option similarity, with a 0 to 100 score. Option similarity was documented before but never used, and ties used to default to "Easy".
- **Quality checks answer support**, not just the question, and ignores filler words and plural forms when matching.
- **Each question has a short explanation.**
- **Errors say what to do next**: rate limit, bad key, unknown model, network.

Difficulty and quality scores are heuristics. They do not prove an answer is factually correct, so review the questions before relying on them.
