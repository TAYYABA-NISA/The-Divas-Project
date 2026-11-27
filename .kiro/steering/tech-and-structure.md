# Technology and Structure

## Stack
- Python, Django 5.1, MySQL (`mysqlclient`). Server-rendered templates with small amounts of vanilla JS.
- PDFs: ReportLab. QR codes: `qrcode` or `segno`. Both are pure Python and install cleanly on Windows.
- Proctoring agent (separate package, separate requirements): opencv-python, mediapipe, ultralytics (YOLOv8n), mss, bleak, numpy, requests.
- Optional AI: `google-genai` (Gemini). Never required.

## Layout
- `accounts/`: users, roles, admin user management.
- `examinations/`: models, forms, views, `services.py`, `permissions.py` (`role_required`), templates.
- `proctoring/` (new): sessions, events, clips, baselines, AI reviews, review decisions, agent API.
- `proctor_agent/` (new, standalone, not deployed with the web app): webcam, YOLO, screen capture, Bluetooth, simulated mode.
- `exam_platform/`: settings and root URLs.
- Requirements: `requirements.txt` for the web app, `proctor_agent/requirements.txt` for the agent.

## Patterns
- Business logic lives in services (`examinations/services.py` and equivalents). Views stay thin.
- Every examiner view uses `role_required` and an ownership check (see `_owned_exam_or_404`).
- Candidate views check `is_candidate` and filter by `request.user`.
- Use transactions and `select_for_update` for attempt start, answer save and finalize.
- Add or change models only with a migration. Do not edit applied migrations.
- Follow existing naming and code style in the repo.

## Commands (run from the project folder, PowerShell)
```powershell
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py runserver
```
Run `runserver` manually in a terminal. Do not start it from automated steps.

## Config
- Settings from environment. Keep `.env.example` current. Never commit `.env`, API keys or tokens.
