# UniConnect

A multi-page Flask portal for university events, society proposals, department-filtered registrations, calendar viewing, user profiles, and notification emails (with optional Gemini API support).

## Features
- **Sign In & Sign Up (`/login`, `/signup`):** Role-based university email validation (`st...@uni.pk`, `s_mem...@uni.pk`, `ad...@uni.pk`) with in-memory session storage.
- **Dedicated Pages:** Separate views for **Dashboard** (`/dashboard`), **Calendar** (`/calendar`), and **Profile** (`/profile`).
- **Department & Event Workflows:** Students see department-specific and all-department events; society members submit/edit requests and add approved events to the calendar; admins manage events and approve/reject society requests.
- **Notifications:** Outbox logging for event and account updates, with optional `GEMINI_API_KEY` integration and safe fallback.

## Run Locally
```bash
pip install flask
python app.py