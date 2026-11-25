"""Web server for the MCQ generator.

Run:  python server.py   then open http://127.0.0.1:8000
"""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

from errors import AppError
from pipeline import MAX_INPUT_CHARS, generate_quiz
from text_extraction import extract_text

load_dotenv()

MAX_UPLOAD_BYTES = 15 * 1024 * 1024

app = Flask(__name__, static_folder="static", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _flag(value, default=False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int(value, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _error(code: str, message: str, status: int):
    return jsonify({"error": code, "message": message}), status


@app.errorhandler(AppError)
def handle_app_error(exc: AppError):
    return _error(exc.code, exc.message, exc.status)


@app.errorhandler(413)
def handle_too_large(_exc):
    mb = MAX_UPLOAD_BYTES // (1024 * 1024)
    return _error("file_too_large", f"That file is larger than {mb} MB. Upload a smaller file.", 413)


@app.errorhandler(404)
def handle_not_found(_exc):
    if request.path.startswith("/api/"):
        return _error("not_found", "That endpoint doesn't exist.", 404)
    return send_from_directory(app.static_folder, "index.html")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/config")
def config():
    return jsonify(
        {
            "has_api_key": bool(_env("GOOGLE_API_KEY")),
            "demo_mode": _flag(_env("DEMO_MODE")),
            "model": _env("GEMINI_MODEL", "gemini-2.5-flash"),
            "max_input_chars": MAX_INPUT_CHARS,
            "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        }
    )


@app.post("/api/generate")
def generate():
    form = request.form
    upload = request.files.get("file")
    pasted = (form.get("text") or "").strip()

    if upload and upload.filename:
        notes = extract_text(upload.filename, upload.read())
        source_name = upload.filename
    elif pasted:
        notes = pasted
        source_name = "Pasted text"
    else:
        raise AppError("no_input", "Upload a PDF or TXT file, or paste your notes.", 400)

    result = generate_quiz(
        notes,
        num_questions=_int(form.get("num_questions"), 5, 1, 10),
        allow_web=_flag(form.get("allow_web"), True),
        max_web_results=_int(form.get("max_web_results"), 3, 1, 5),
        topic=(form.get("topic") or "").strip()[:200],
        api_key=_env("GOOGLE_API_KEY"),
        model_name=_env("GEMINI_MODEL", "gemini-2.5-flash"),
        demo=_flag(_env("DEMO_MODE")),
    )
    result["meta"]["source_name"] = source_name
    return jsonify(result)


if __name__ == "__main__":
    port = int(_env("PORT", "8000") or 8000)
    app.run(host="127.0.0.1", port=port, debug=_flag(_env("FLASK_DEBUG")))
