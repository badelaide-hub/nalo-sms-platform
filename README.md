# Nalo SMS Platform

A Python/Flask web application integrated with the **Nalo Solutions SMS API** for sending single and bulk SMS messages, tracking real-time delivery reports via webhooks, and exporting persistent message logs to CSV.

* **Live Application:** https://nalo-sms-platform.onrender.com/
* **Source Repository:** https://github.com/badelaide-hub/nalo-sms-platform

---

## What the App Does

* **SMS Dispatch:** Sends single or bulk SMS messages with custom Sender IDs through the Nalo Solutions API.
* **Real-Time Delivery Callbacks:** Exposes a webhook endpoint (`/callback`) that listens for Nalo Delivery Reports (DLR) and automatically updates message statuses in the database (`SUBMITTED` → `DELIVERED`, `UNDELIVERABLE`, `EXPIRED`, etc.).
* **Persistent Message History:** Uses **PostgreSQL** (`DATABASE_URL`) so message records and delivery statuses remain intact across page refreshes, server restarts, and Render redeployments.
* **CSV Report Export:** Generates and downloads full SMS activity reports—including UTC timestamps, recipient numbers, Sender IDs, message IDs, and delivery statuses—as a `.csv` file.

---

## Environment Variables

Create a `.env` file in the root directory of the project (ensure `.env` is in your `.gitignore` so credentials are never committed) and configure the following variables:

| Variable | Required | Description | Example |
| :--- | :---: | :--- | :--- |
| `NALO_API_KEY` | Yes* | Your Nalo Solutions API authentication key (used instead of username/password). | `your_nalo_api_key` |
| `NALO_USERNAME` | Yes* | Your Nalo account username (required if not using `NALO_API_KEY`). | `adelaidebaah` |
| `NALO_PASSWORD` | Yes* | Your Nalo account password (required if not using `NALO_API_KEY`). | `your_password` |
| `NALO_SENDER_ID` | Yes | Approved alphanumeric Sender ID (max 11 characters) shown on recipient devices. | `ADELLE` |
| `CALLBACK_URL` | Yes | Public HTTPS URL where Nalo sends delivery report callbacks. | `https://nalo-sms-platform.onrender.com/callback` |
| `DATABASE_URL` | Yes | PostgreSQL connection string (`postgresql://...`) for persistent message storage. | `your_database_url` |
| `SECRET_KEY` | Yes | Flask secret key used for session signing and CSRF protection. | `your_secret_key` |
| `PORT` | No | Port the web server binds to (defaults to `5000` locally; set automatically by Render). | `5000` |

*\*Provide either `NALO_API_KEY` or the `NALO_USERNAME` + `NALO_PASSWORD` pair.*

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
