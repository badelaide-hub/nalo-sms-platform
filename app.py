import csv
import io
import json
import os
import re
from datetime import datetime, timezone
import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

default_sqlite = f"sqlite:///{os.path.join(DATA_DIR, 'sms_platform.db')}"
database_url = os.getenv("DATABASE_URL", default_sqlite).strip()
if database_url.startswith("sqlite:///./"):
    rel_path = database_url.replace("sqlite:///./", "", 1)
    database_url = f"sqlite:///{os.path.join(BASE_DIR, rel_path)}"
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
if database_url.startswith("sqlite"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"connect_args": {"timeout": 30}}

db = SQLAlchemy(app)

NALO_SEND_URL = "https://sms.nalosolutions.com/smsbackend/Resl_Nalo/send-message/"


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()


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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "message_id": self.message_id or "-",
            "recipient": self.recipient,
            "sender_id": self.sender_id,
            "message": self.message,
            "status": self.status,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
        }


with app.app_context():
    try:
        db.create_all()
    except Exception as exc:
        app.logger.warning("Database initialization notice: %s", exc)


def get_allowed_sender_ids() -> list[str]:
    raw = os.getenv("SENDER_IDS", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def normalize_phone_number(raw: str) -> str | None:
    cleaned = re.sub(r"[\s\-\(\)]", "", str(raw or "").strip())
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    # Convert local Ghana 10-digit numbers (024XXXXXXX) to 23324XXXXXXX
    if re.fullmatch(r"0[235]\d{8}", cleaned):
        cleaned = "233" + cleaned[1:]
    if re.fullmatch(r"[1-9]\d{9,14}", cleaned):
        return cleaned
    return None


def parse_recipients(raw_numbers: str, contacts_json: str) -> tuple[list[dict], str | None]:
    contacts_map: dict[str, dict] = {}

    if contacts_json:
        try:
            parsed_contacts = json.loads(contacts_json)
            if isinstance(parsed_contacts, list):
                for entry in parsed_contacts:
                    if not isinstance(entry, dict):
                        continue
                    norm = normalize_phone_number(entry.get("phone", ""))
                    if norm and norm not in contacts_map:
                        contacts_map[norm] = {
                            "phone": norm,
                            "name": str(entry.get("name", "")).strip(),
                        }
        except ValueError:
            pass

    if raw_numbers and raw_numbers.strip():
        parts = [p.strip() for p in re.split(r"[,;\n]+", raw_numbers) if p.strip()]
        for num in parts:
            norm = normalize_phone_number(num)
            if not norm:
                return (
                    [],
                    f"Invalid phone number '{num}'. Use international format (e.g., 23324XXXXXXX) or 10-digit Ghana format (024XXXXXXX).",
                )
            if norm not in contacts_map:
                contacts_map[norm] = {"phone": norm, "name": ""}

    if not contacts_map:
        return [], "Please enter at least one valid phone number or upload a contact list."

    return list(contacts_map.values()), None


def normalize_delivery_status(raw_status: str) -> str:
    val = str(raw_status or "").strip().upper()
    if val in {"DELIVRD", "DELIVERED", "SUCCESS", "1701", "0"}:
        return "DELIVERED"
    if val in {"UNDELIV", "UNDELIVERED", "FAILED", "REJECTED", "EXPIRED", "ERROR"}:
        return "UNDELIVERED"
    return val or "UPDATED"


def extract_message_id(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    raw_id = (
        data.get("job_id")
        or data.get("message_id")
        or data.get("msg_id")
        or data.get("id")
        or nested.get("job_id")
        or nested.get("message_id")
        or nested.get("msg_id")
        or nested.get("id")
    )
    return str(raw_id).strip() if raw_id else None


def compute_stats() -> dict:
    total = SmsMessage.query.count()
    delivered = SmsMessage.query.filter_by(status="DELIVERED").count()
    submitted = SmsMessage.query.filter(
        SmsMessage.status.in_(["SUBMITTED", "PENDING"])
    ).count()
    failed = SmsMessage.query.filter(
        SmsMessage.status.in_(["FAILED", "UNDELIVERED"])
    ).count()
    rate = round((delivered / total) * 100, 1) if total > 0 else 0.0
    return {
        "total": total,
        "delivered": delivered,
        "submitted": submitted,
        "failed": failed,
        "delivery_rate": rate,
    }


def dispatch_nalo_sms(
    api_key: str,
    recipients: list[str],
    message_text: str,
    sender_id: str,
    callback_url: str,
) -> tuple[bool, str | None, str]:
    payload = {
        "key": api_key,
        "msisdn": ",".join(recipients),
        "message": message_text,
        "sender_id": sender_id,
        "dlr": "1",
    }
    if callback_url:
        payload["callback_url"] = callback_url

    resp = requests.post(NALO_SEND_URL, json=payload, timeout=15)
    raw_body = resp.text
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": raw_body}

    msg_id = extract_message_id(data)
    accepted = resp.status_code in (200, 201) and str(
        data.get("status", "")
    ).lower() not in (
        "error",
        "failed",
        "1702",
        "1703",
        "1704",
        "1705",
        "1706",
        "1713",
    )
    return accepted, msg_id, raw_body


@app.route("/", methods=["GET"])
def index():
    sender_ids = get_allowed_sender_ids()
    messages = SmsMessage.query.order_by(SmsMessage.created_at.desc()).limit(100).all()
    stats = compute_stats()
    return render_template(
        "index.html", sender_ids=sender_ids, messages=messages, stats=stats
    )


@app.route("/api/messages", methods=["GET"])
def list_messages():
    messages = SmsMessage.query.order_by(SmsMessage.created_at.desc()).limit(100).all()
    return jsonify(
        {
            "messages": [m.to_dict() for m in messages],
            "stats": compute_stats(),
        }
    )


@app.route("/send", methods=["POST"])
def send_sms():
    allowed_senders = get_allowed_sender_ids()
    raw_numbers = request.form.get("numbers", "")
    contacts_json = request.form.get("contacts_json", "")
    sender_id = request.form.get("sender_id", "").strip()
    message_template = request.form.get("message", "").strip()

    if not sender_id or sender_id not in allowed_senders:
        flash("Please select a valid Sender ID from the list.", "error")
        return redirect(url_for("index"))

    if not message_template:
        flash("Message body cannot be empty.", "error")
        return redirect(url_for("index"))

    contacts, error = parse_recipients(raw_numbers, contacts_json)
    if error:
        flash(error, "error")
        return redirect(url_for("index"))

    api_key = os.getenv("SMS_API_KEY", "").strip()
    if not api_key or api_key == "your_nalo_api_key_here":
        flash("Server configuration error: SMS_API_KEY is not set.", "error")
        return redirect(url_for("index"))

    callback_base = os.getenv(
        "CALLBACK_BASE_URL", "https://nalo-sms-platform.onrender.com"
    ).strip().rstrip("/")
    callback_url = f"{callback_base}/api/callback" if callback_base else ""

    uses_personalization = "{name}" in message_template

    try:
        accepted_count = 0
        failed_count = 0
        last_raw = ""

        if uses_personalization:
            for contact in contacts:
                display_name = contact["name"] or "Customer"
                personalized_msg = message_template.replace("{name}", display_name)
                accepted, msg_id, raw_body = dispatch_nalo_sms(
                    api_key, [contact["phone"]], personalized_msg, sender_id, callback_url
                )
                last_raw = raw_body
                if accepted:
                    accepted_count += 1
                else:
                    failed_count += 1
                db.session.add(
                    SmsMessage(
                        message_id=msg_id,
                        recipient=contact["phone"],
                        sender_id=sender_id,
                        message=personalized_msg,
                        status="SUBMITTED" if accepted else "FAILED",
                        api_response=raw_body,
                    )
                )
        else:
            phone_list = [c["phone"] for c in contacts]
            accepted, msg_id, raw_body = dispatch_nalo_sms(
                api_key, phone_list, message_template, sender_id, callback_url
            )
            last_raw = raw_body
            if accepted:
                accepted_count = len(phone_list)
            else:
                failed_count = len(phone_list)

            for phone in phone_list:
                db.session.add(
                    SmsMessage(
                        message_id=msg_id,
                        recipient=phone,
                        sender_id=sender_id,
                        message=message_template,
                        status="SUBMITTED" if accepted else "FAILED",
                        api_response=raw_body,
                    )
                )

        db.session.commit()

        if accepted_count > 0 and failed_count == 0:
            flash(
                f"Successfully submitted {accepted_count} SMS message(s) to Nalo.",
                "success",
            )
        elif accepted_count > 0:
            flash(
                f"Submitted {accepted_count} message(s), {failed_count} failed. Last response: {last_raw}",
                "error",
            )
        else:
            flash(f"Nalo API rejected the request: {last_raw}", "error")

    except requests.RequestException as exc:
        flash(f"Network error contacting Nalo API: {exc}", "error")
    except Exception as exc:
        db.session.rollback()
        app.logger.exception("Error processing SMS request")
        flash(f"Error processing SMS request: {exc}", "error")

    return redirect(url_for("index"))


@app.route("/api/callback", methods=["GET", "POST"])
def delivery_callback():
    payload = {}
    if request.is_json:
        payload.update(request.get_json(silent=True) or {})
    if request.form:
        payload.update(request.form.to_dict())
    if request.args:
        payload.update(request.args.to_dict())

    app.logger.info("Delivery callback received: %s", json.dumps(payload))

    job_id = str(
        payload.get("job_id")
        or payload.get("message_id")
        or payload.get("msg_id")
        or payload.get("id")
        or ""
    ).strip()
    raw_recipient = str(
        payload.get("msisdn")
        or payload.get("recipient")
        or payload.get("destination")
        or payload.get("phone")
        or ""
    ).strip()
    recipient = raw_recipient[1:] if raw_recipient.startswith("+") else raw_recipient
    raw_status = (
        payload.get("status")
        or payload.get("dlr_status")
        or payload.get("delivery_status")
        or payload.get("state")
        or ""
    )

    if not job_id and not recipient:
        return jsonify({"ok": False, "error": "Missing message_id/job_id or msisdn"}), 400

    query = SmsMessage.query
    if job_id:
        query = query.filter_by(message_id=job_id)
    if recipient:
        query = query.filter_by(recipient=recipient)

    matches = query.order_by(SmsMessage.created_at.desc()).all()
    if not matches and recipient:
        matches = (
            SmsMessage.query.filter_by(recipient=recipient, status="SUBMITTED")
            .order_by(SmsMessage.created_at.desc())
            .limit(1)
            .all()
        )

    new_status = normalize_delivery_status(raw_status)
    for record in matches:
        record.status = new_status
        record.api_response = json.dumps(payload)

    db.session.commit()
    return jsonify({"ok": True, "updated": len(matches), "status": new_status}), 200


@app.route("/export/csv", methods=["GET"])
def export_csv():
    messages = SmsMessage.query.order_by(SmsMessage.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["ID", "Time (UTC)", "Recipient", "Sender ID", "Message", "Message ID", "Status"]
    )
    for m in messages:
        writer.writerow(
            [
                m.id,
                m.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                m.recipient,
                m.sender_id,
                m.message,
                m.message_id or "-",
                m.status,
            ]
        )

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=nalo_sms_report.csv"},
    )


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
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
