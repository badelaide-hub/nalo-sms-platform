# Nalo SMS Platform

A containerized web application built with Flask that sends single and bulk SMS messages via the Nalo SMS API, validates phone numbers and inputs, receives delivery reports via webhook callbacks, and updates message statuses in real time[cite: 4, 14].

## Features

- **Send SMS Form:** Supports single or comma-separated international phone numbers (e.g., `233XXXXXXXXX`), local 10-digit Ghanaian number normalization (`024XXXXXXX` → `23324XXXXXXX`), dynamic Sender ID selection from environment configuration, and a live character/segment counter[cite: 4, 14].
- **Input Validation:** Rejects empty messages, unselected/unauthorized Sender IDs, and malformed phone numbers prior to calling the Nalo API[cite: 4, 14].
- **Real-Time Delivery Reports:** Exposes `/api/callback` to capture Nalo delivery status updates (`DELIVERED`, `UNDELIVERED`, etc.) and polls `/api/messages` automatically so the UI updates without a manual page refresh[cite: 4, 14].
- **Persistent History:** Stores sent messages and delivery statuses in SQLite (via a Docker volume locally) or PostgreSQL (in production)[cite: 5, 14].
- **CSV Reporting:** Exports full message and delivery report history via `/export/csv`.

## Live Deployment

- **Live URL:** https://nalo-sms-platform.onrender.com[cite: 2]

## Quick Start with Docker

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/badelaide-hub/nalo-sms-platform.git](https://github.com/badelaide-hub/nalo-sms-platform.git)[cite: 1]
   cd nalo-sms-platform[cite: 14]