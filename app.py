import os
import re
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

default_sqlite = f"sqlite:///{os.path.join(DATA_DIR, 'sms_platform.db')}"
database_url = os.getenv("DATABASE_URL", default_sqlite)
if database_url.startswith("sqlite:///./"):
    rel_path = database_url.replace("sqlite:///./", "", 1)
    database_url = f"sqlite:///{os.path.join(BASE_DIR, rel_path)}"
# Ensure SQLAlchemy uses psycopg v3 for PostgreSQL URLs
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

NALO_SEND_URL = "https://sms.nalosolutions.com/smsbackend/Resl_Nalo/send-message/"


class SmsMessage(db.Model):
    __tablename__ = "sms_messages"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.String(120), nullable=True, index=True)
    recipient = db.Column(db.String(32), nullable=False, index=True)
    sender_id = db.Column(db.String(32), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(64), nullable=False, default="PENDING")
    api_response = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


with app.app_context():
    db.create_all()


def get_allowed_sender_ids() -> list[str]:
    raw = os.getenv("SENDER_IDS", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def parse_and_validate_numbers(raw_numbers: str) -> tuple[list[str], str | None]:
    if not raw_numbers or not raw_numbers.strip():
        return [], "Please enter at least one phone number."

    parts = [p.strip() for p in raw_numbers.split(",") if p.strip()]
    if not parts:
        return [], "Please enter at least one valid phone number."

    valid_numbers = []
    for num in parts:
        # Strip leading '+' if entered, then enforce international digits-only format (10-15 digits, e.g., 233XXXXXXXXX)
        cleaned = num[1:] if num.startswith("+") else num
        if not re.fullmatch(r"[1-9]\d{9,14}", cleaned):
            return (
                [],
                f"Invalid phone number '{num}'. Use international format without '+' (e.g., 233XXXXXXXXX).",
            )
        valid_numbers.append(cleaned)

    return valid_numbers, None


@app.route("/", methods=["GET"])
def index():
    sender_ids = get_allowed_sender_ids()
    messages = SmsMessage.query.order_by(SmsMessage.created_at.desc()).limit(50).all()
    return render_template("index.html", sender_ids=sender_ids, messages=messages)


@app.route("/send", methods=["POST"])
def send_sms():
    allowed_senders = get_allowed_sender_ids()
    raw_numbers = request.form.get("numbers", "")
    sender_id = request.form.get("sender_id", "").strip()
    message_text = request.form.get("message", "").strip()

    # 1. Validate inputs before touching the API
    if not sender_id or sender_id not in allowed_senders:
        flash("Please select a valid Sender ID from the list.", "error")
        return redirect(url_for("index"))

    if not message_text:
        flash("Message body cannot be empty.", "error")
        return redirect(url_for("index"))

    numbers, error = parse_and_validate_numbers(raw_numbers)
    if error:
        flash(error, "error")
        return redirect(url_for("index"))

    api_key = os.getenv("SMS_API_KEY", "").strip()
    if not api_key or api_key == "your_nalo_api_key_here":
        flash("Server configuration error: SMS_API_KEY is not set.", "error")
        return redirect(url_for("index"))

    callback_base = os.getenv("CALLBACK_BASE_URL", "").rstrip("/")
    callback_url = f"{callback_base}/api/callback" if callback_base else ""

    payload = {
        "key": api_key,
        "msisdn": ",".join(numbers),
        "message": message_text,
        "sender_id": sender_id,
    }
    if callback_url:
        payload["callback_url"] = callback_url

    # 2. Call Nalo SMS API
    try:
        resp = requests.post(NALO_SEND_URL, json=payload, timeout=15)
        raw_body = resp.text
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": raw_body}

        msg_id = None
        if isinstance(data, dict):
            msg_id = (
                data.get("message_id")
                or data.get("job_id")
                or data.get("id")
                or (data.get("data", {}) if isinstance(data.get("data"), dict) else {}).get("message_id")
            )

        accepted = resp.status_code in (200, 201) and str(data.get("status", "")).lower() not in (
            "error",
            "failed",
            "1702",
            "1703",
            "1704",
            "1705",
            "1706",
            "1713",
        )
        initial_status = "SUBMITTED" if accepted else "FAILED"

        for num in numbers:
            record = SmsMessage(
                message_id=str(msg_id) if msg_id else None,
                recipient=num,
                sender_id=sender_id,
                message=message_text,
                status=initial_status,
                api_response=raw_body,
            )
            db.session.add(record)
        db.session.commit()

        if accepted:
            id_info = f" (Message ID: {msg_id})" if msg_id else ""
            flash(f"SMS accepted by Nalo API{id_info}. Response: {raw_body}", "success")
        else:
            flash(f"Nalo API rejected the request: {raw_body}", "error")

    except requests.RequestException as exc:
        flash(f"Network error contacting Nalo API: {exc}", "error")

    return redirect(url_for("index"))


@app.route("/delete/<int:msg_db_id>", methods=["POST"])
def delete_message(msg_db_id):
    record = db.session.get(SmsMessage, msg_db_id)
    if record:
        db.session.delete(record)
        db.session.commit()
        flash("Message deleted.", "success")
    return redirect(url_for("index"))


@app.route("/clear", methods=["POST"])
def clear_history():
    try:
        db.session.query(SmsMessage).delete()
        db.session.commit()
        flash("All message history cleared.", "success")
    except Exception as exc:
        db.session.rollback()
        flash(f"Failed to clear history: {exc}", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)