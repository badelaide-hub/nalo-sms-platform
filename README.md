# Nalo SMS Platform

A Python/Flask web application integrated with the **Nalo Solutions SMS API** for sending single and bulk SMS messages, tracking real-time delivery reports via webhooks, and exporting persistent message logs to CSV.

- **Live Application:** https://nalo-sms-platform.onrender.com/
- **Health Check:** https://nalo-sms-platform.onrender.com/health
- **Source Repository:** https://github.com/badelaide-hub/nalo-sms-platform

---

## What the App Does

- **SMS Dispatch:** Sends single or bulk SMS messages (with optional `{name}` personalization) using approved Sender IDs through the Nalo Solutions API.
- **Real-Time Delivery Callbacks:** Exposes a webhook endpoint (`/api/callback`) that accepts both `GET` and `POST` Nalo Delivery Reports (DLR) and automatically updates message statuses in the database (`SUBMITTED` → `DELIVERED`, `UNDELIVERABLE`, `EXPIRED`, etc.).
- **Persistent Message History:** Uses **PostgreSQL** (`DATABASE_URL`) in production (with SQLite fallback locally) so message records and delivery statuses remain intact across page refreshes, server restarts, and Render redeployments.
- **CSV Report Export:** Generates and downloads full SMS activity reports—including UTC timestamps, recipient numbers, Sender IDs, message IDs, and delivery statuses—as `nalo_sms_report.csv`.

---

## Environment Variables

Create a `.env` file in the root directory of the project (ensure `.env` is in your `.gitignore` so credentials are never committed) and configure the following variables:

| Variable | Required | Description | Example |
| :--- | :---: | :--- | :--- |
| `SMS_API_KEY` | Yes | Your Nalo Solutions API authentication key. | `your_nalo_api_key` |
| `SENDER_IDS` | Yes | Comma-separated list of approved alphanumeric Sender IDs (max 11 characters). | `ADELLE` |
| `CALLBACK_BASE_URL` | Yes | Public HTTPS base URL where Nalo sends delivery report callbacks (the app appends `/api/callback` automatically). | `https://nalo-sms-platform.onrender.com` |
| `DATABASE_URL` | Yes | PostgreSQL connection string (`postgresql://...`) for persistent message storage (defaults to local SQLite if omitted). | `your_database_url` |
| `FLASK_SECRET_KEY` | Yes | Flask secret key used for session signing and flash messages. | `your_secret_key` |

---

## How to Run with Docker

### Option 1: Docker Compose (App + Local PostgreSQL)
If you are using `docker-compose.yml` to run both the Flask web app and a local PostgreSQL container together:

```bash
# 1. Clone the repository
git clone [https://github.com/badelaide-hub/nalo-sms-platform.git](https://github.com/badelaide-hub/nalo-sms-platform.git)
cd nalo-sms-platform

# 2. Copy the environment template and add your credentials
cp .env.example .env

# 3. Build and start the containers
docker compose up --build
