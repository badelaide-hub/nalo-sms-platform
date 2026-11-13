# Nalo SMS Platform

A containerized web application built with Flask that sends single and bulk SMS messages via the Nalo SMS API, validates phone numbers and inputs, receives delivery reports via webhook callbacks, and updates message statuses in real time.

## Features
- **Send SMS Form:** Supports single or comma-separated international phone numbers (e.g., `233XXXXXXXXX`), dynamic Sender ID selection from environment configuration, and a live character/segment counter.
- **Input Validation:** Rejects empty messages, unselected/unauthorized Sender IDs, and malformed phone numbers prior to calling the Nalo API.
- **Real-Time Delivery Reports:** Exposes `/api/callback` to capture Nalo delivery status updates (`DELIVERED`, `UNDELIVERED`, etc.) and polls `/api/messages` every 5 seconds so the UI updates automatically without a manual page refresh.
- **Persistent History:** Stores sent messages and delivery statuses in SQLite (via a Docker volume locally) or PostgreSQL (in production).

## Live Deployment
- **Live URL:** *(Add deployed HTTPS URL here once live)*

## Quick Start with Docker

1. **Clone the repository:**
   ```bash
   git clone <your-public-repo-url>
   cd nalo-sms-platform