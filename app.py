"""Morrow — a small, deployable web calendar.

The original project was a Tkinter desktop application. This Flask entry point
provides the browser version used by Render. It supports PostgreSQL through
DATABASE_URL and falls back to a local SQLite database for development.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Boolean, DateTime, Integer, String, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = BASE_DIR / "morrow.db"

COLORS = {
    "Coral": ("#c65d6e", "#f7e1e0"),
    "Marigold": ("#c88b24", "#faedc9"),
    "Teal": ("#4a9284", "#dceee8"),
    "Plum": ("#795b85", "#e9e0ec"),
    "Ink": ("#4b5872", "#e3e8f0"),
}
REMINDERS = {0, 1, 7}
EVENT_TYPES = {"birthday", "event"}


def database_url() -> str:
    configured = os.getenv("DATABASE_URL", "").strip()
    if not configured:
        return f"sqlite:///{DEFAULT_DATABASE}"
    if configured.startswith("postgres://"):
        return configured.replace("postgres://", "postgresql+psycopg://", 1)
    if configured.startswith("postgresql://"):
        return configured.replace("postgresql://", "postgresql+psycopg://", 1)
    return configured


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Event(db.Model):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    time: Mapped[str] = mapped_column(String(5), default="", nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="Coral", nullable=False)
    reminder: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32),
    SQLALCHEMY_DATABASE_URI=database_url(),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0").lower() in {"1", "true", "yes"},
)
db.init_app(app)


def event_dict(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "title": event.title,
        "date": event.date,
        "type": event.type,
        "time": event.time,
        "color": event.color,
        "reminder": event.reminder,
        "notes": event.notes,
        "all_day": event.all_day,
    }


def validate_event(payload: Any, existing: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."

    source = {**(existing or {}), **payload}
    title = str(source.get("title", "")).strip()
    date_value = str(source.get("date", "")).strip()
    event_type = str(source.get("type", "event")).strip().lower()
    color = str(source.get("color", "Coral"))
    notes = str(source.get("notes", "") or "").strip()
    all_day = bool(source.get("all_day", source.get("allDay", True)))
    event_time = "" if all_day else str(source.get("time", "") or "").strip()

    if not title:
        return None, "A title is required."
    try:
        datetime.strptime(date_value, "%Y-%m-%d")
    except ValueError:
        return None, "Date must use YYYY-MM-DD format."
    if event_type not in EVENT_TYPES:
        return None, "Type must be event or birthday."
    if color not in COLORS:
        return None, "Choose a supported calendar color."
    if event_time:
        try:
            datetime.strptime(event_time, "%H:%M")
        except ValueError:
            return None, "Time must use HH:MM format."

    try:
        reminder = int(source.get("reminder", 0))
    except (TypeError, ValueError):
        return None, "Reminder must be 0, 1, or 7 days."
    if reminder not in REMINDERS:
        return None, "Reminder must be 0, 1, or 7 days."

    return {
        "id": str(source.get("id") or uuid.uuid4()),
        "title": title,
        "date": date_value,
        "type": event_type,
        "time": event_time,
        "color": color,
        "reminder": reminder,
        "notes": notes,
        "all_day": all_day,
    }, None


def current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_required(view: Callable) -> Callable:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        if current_user() is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please sign in first."}), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.context_processor
def template_context() -> dict[str, Any]:
    return {"csrf_token": csrf_token, "current_user": current_user()}


@app.before_request
def verify_csrf() -> Any:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if request.endpoint == "login":
        return None

    expected = session.get("csrf_token")
    provided = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    if not expected or not provided or not hmac.compare_digest(expected, provided):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Invalid security token. Refresh and try again."}), 400
        return "Invalid security token. Refresh and try again.", 400
    return None


def initialise_database() -> None:
    with app.app_context():
        db.create_all()
        if not db.session.query(User).first():
            admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
            if admin_password:
                admin_username = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
                db.session.add(
                    User(
                        username=admin_username,
                        password_hash=generate_password_hash(admin_password),
                    )
                )
                db.session.commit()


@app.get("/healthz")
def healthz():
    try:
        with app.app_context():
            db.session.execute(text("SELECT 1"))
            has_user = db.session.query(User).first() is not None
        return jsonify({"status": "ok", "service": "morrow-calendar", "auth_configured": has_user})
    except Exception as error:  # noqa: BLE001 - health endpoint must report deployment failures.
        return jsonify({"status": "error", "message": str(error)}), 503


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user() is not None:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.session.query(User).filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            csrf_token()
            destination = request.args.get("next", "")
            return redirect(destination if destination.startswith("/") else url_for("index"))
        error = "The username or password is incorrect."

    has_user = db.session.query(User).first() is not None
    return render_template("login.html", error=error, has_user=has_user)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    return render_template("index.html")


@app.get("/api/events")
@login_required
def list_events():
    events = db.session.query(Event).order_by(Event.date, Event.title).all()
    return jsonify({"events": [event_dict(event) for event in events]})


@app.post("/api/events")
@login_required
def create_event():
    payload, error = validate_event(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400
    event = Event(**payload)
    db.session.add(event)
    db.session.commit()
    return jsonify({"event": event_dict(event)}), 201


@app.put("/api/events/<event_id>")
@login_required
def update_event(event_id: str):
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404
    payload, error = validate_event(request.get_json(silent=True), event_dict(event))
    if error:
        return jsonify({"error": error}), 400
    for key, value in payload.items():
        setattr(event, key, value)
    db.session.commit()
    return jsonify({"event": event_dict(event)})


@app.delete("/api/events/<event_id>")
@login_required
def delete_event(event_id: str):
    event = db.session.get(Event, event_id)
    if not event:
        return jsonify({"error": "Event not found."}), 404
    db.session.delete(event)
    db.session.commit()
    return jsonify({"deleted": event_id})


@app.post("/api/import")
@login_required
def import_events():
    payload = request.get_json(silent=True)
    raw_events = payload.get("events", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_events, list):
        return jsonify({"error": "Import must contain an events list."}), 400

    imported: list[dict[str, Any]] = []
    for raw in raw_events:
        event, error = validate_event(raw)
        if error:
            return jsonify({"error": f"Invalid event: {error}"}), 400
        imported.append(event)

    db.session.query(Event).delete()
    db.session.add_all(Event(**event) for event in imported)
    db.session.commit()
    return jsonify({"events": imported, "count": len(imported)})


@app.get("/api/integrations")
@login_required
def integrations():
    """Return configuration status only; never return secret values."""

    return jsonify(
        {
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "tavily": bool(os.getenv("TAVILY_API_KEY")),
            "groq": bool(os.getenv("GROQ_API_KEY")),
        }
    )


def provider_request(url: str, api_key: str, payload: dict[str, Any], *, provider: str) -> dict[str, Any]:
    """Call an AI provider without ever logging or returning the API key."""

    if provider == "tavily":
        headers = {"Content-Type": "application/json"}
    else:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
    encoded = json.dumps(payload).encode("utf-8")
    request_object = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request_object, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{provider.title()} request failed with status {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{provider.title()} request could not be completed.") from error


def tavily_research(query: str) -> list[dict[str, str]]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    response = provider_request(
        "https://api.tavily.com/search",
        api_key,
        {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5,
            "include_answer": False,
            "include_raw_content": False,
        },
        provider="tavily",
    )
    return [
        {
            "title": str(item.get("title", "")).strip(),
            "content": str(item.get("content", "")).strip()[:500],
            "url": str(item.get("url", "")).strip(),
        }
        for item in response.get("results", [])
        if isinstance(item, dict) and item.get("title")
    ]


def llm_suggestions(prompt: str, month: str, research: list[dict[str, str]], provider: str) -> list[dict[str, Any]]:
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        endpoint = "https://api.openai.com/v1/chat/completions"
        model = "gpt-4o-mini"
    else:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        endpoint = "https://api.groq.com/openai/v1/chat/completions"
        model = "llama-3.3-70b-versatile"

    if not api_key:
        return []

    research_text = "\n".join(
        f"- {item['title']}: {item['content']}" for item in research
    ) or "No web research was available."
    system_message = (
        "You create practical birthday and event ideas for a personal calendar. "
        "Return only valid JSON: an object with a 'suggestions' array. Each item "
        "must contain title, date (YYYY-MM-DD), type (event or birthday), and notes. "
        "Suggest 3 to 5 useful ideas. Do not invent a date outside the requested "
        "month unless the user explicitly asks for a recurring birthday."
    )
    user_message = (
        f"Requested month: {month or 'the next suitable month'}\n"
        f"User request: {prompt}\n"
        f"Optional research from Tavily:\n{research_text}"
    )
    response = provider_request(
        endpoint,
        api_key,
        {
            "model": model,
            "temperature": 0.7,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
        },
        provider=provider,
    )
    content = response["choices"][0]["message"]["content"]
    decoded = json.loads(content)
    suggestions = decoded.get("suggestions", decoded) if isinstance(decoded, dict) else decoded
    if not isinstance(suggestions, list):
        raise RuntimeError("The AI provider returned an invalid suggestions format.")
    return suggestions


def normalise_suggestions(raw: list[Any], fallback_month: str) -> list[dict[str, Any]]:
    fallback_date = f"{fallback_month}-01" if len(fallback_month) == 7 else datetime.utcnow().strftime("%Y-%m-%d")
    normalised: list[dict[str, Any]] = []
    for item in raw[:5]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()[:120]
        if not title:
            continue
        date_value = str(item.get("date", fallback_date)).strip()
        try:
            datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            date_value = fallback_date
        event_type = str(item.get("type", "event")).lower()
        if event_type not in EVENT_TYPES:
            event_type = "event"
        normalised.append(
            {
                "title": title,
                "date": date_value,
                "type": event_type,
                "notes": str(item.get("notes", "")).strip()[:1000],
                "color": "Coral" if event_type == "birthday" else "Teal",
                "reminder": 1,
                "all_day": True,
            }
        )
    return normalised


@app.post("/api/ai/suggestions")
@login_required
def ai_suggestions():
    payload = request.get_json(silent=True) or {}
    prompt = str(payload.get("prompt", "")).strip()[:500]
    month = str(payload.get("month", "")).strip()
    requested_provider = str(payload.get("provider", "auto")).lower()
    if not prompt:
        return jsonify({"error": "Tell the assistant what kind of dates you want."}), 400

    available = {
        "openai": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "groq": bool(os.getenv("GROQ_API_KEY", "").strip()),
        "tavily": bool(os.getenv("TAVILY_API_KEY", "").strip()),
    }
    if requested_provider not in {"auto", "openai", "groq"}:
        requested_provider = "auto"
    llm_provider = (
        requested_provider
        if requested_provider in {"openai", "groq"} and available[requested_provider]
        else "openai" if available["openai"] else "groq" if available["groq"] else ""
    )
    if not llm_provider and not available["tavily"]:
        return jsonify({"error": "Add an OpenAI, Groq, or Tavily key in Render Environment settings first."}), 503

    research: list[dict[str, str]] = []
    research_error = None
    if available["tavily"]:
        try:
            research = tavily_research(f"{prompt} event ideas {month}".strip())
        except RuntimeError:
            research_error = "Tavily research was unavailable, so the assistant continued without web research."

    suggestions: list[dict[str, Any]] = []
    provider_used = "tavily"
    if llm_provider:
        try:
            suggestions = normalise_suggestions(llm_suggestions(prompt, month, research, llm_provider), month)
            provider_used = llm_provider
        except (RuntimeError, KeyError, TypeError, json.JSONDecodeError) as error:
            if not research:
                return jsonify({"error": str(error)}), 502

    if not suggestions:
        suggestions = normalise_suggestions(
            [
                {
                    "title": result["title"],
                    "date": f"{month}-01" if len(month) == 7 else "",
                    "type": "event",
                    "notes": result["content"],
                }
                for result in research
            ],
            month,
        )

    return jsonify(
        {
            "provider": provider_used,
            "research_count": len(research),
            "warning": research_error,
            "suggestions": suggestions,
        }
    )


initialise_database()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)