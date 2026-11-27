# Technoverse 5.0: Secure Examination Management System

A Django 5.1 examination platform for the Technoverse Web-e-Thon. Institutions can create, deliver, monitor, grade and publish online examinations. The project is built around three roles: administrator, examiner and candidate.

## Current implementation

- Role-aware sign-in and backend-protected examiner and candidate workflows.
- Exam creation, reusable question bank, candidate enrollment, attempt snapshots, autosave and server-side time limits.
- Demo data command with fictional accounts and Easy, Medium and Hard questions.
- Candidate workspace preferences (font size, high contrast, palette position and density) saved server-side, plus a private autosaved scratchpad that is never graded.
- CSV/JSON question and candidate imports with templates, validation previews, row-level errors and atomic commit.
- Examiner sandbox previews, excluded from real candidate access, monitoring, grading, analytics, results and reports.
- Downloadable ReportLab PDFs with QR/manual verification IDs and minimal public verification data.
- Consent-based proctoring sessions, private examiner-only evidence, advisory event review and a simulated local agent.
- Implementation plan and requirement traceability in [`.kiro/specs/technoverse-exam-platform/`](.kiro/specs/technoverse-exam-platform/).

## Prerequisites

- Python supported by Django 5.1 (Python 3.10+ recommended).
- MySQL or MariaDB with a database and user for the web application.
- A virtual environment.
- A C compiler/MySQL client development libraries if your platform requires them to install `mysqlclient`.

## Web application setup

Run all commands from the project folder:

```powershell
cd "C:\Users\W.Moazzam's laptop\OneDrive\Documents\Technoverse webethon"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Create a MySQL database and account, then export the settings for the current PowerShell session:

```powershell
$env:DJANGO_SECRET_KEY = "replace-with-a-long-random-secret"
$env:DJANGO_DEBUG = "true"
$env:DJANGO_ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:DJANGO_TIME_ZONE = "Asia/Karachi"
$env:MYSQL_DATABASE = "exam_platform"
$env:MYSQL_USER = "exam_user"
$env:MYSQL_PASSWORD = "replace-with-your-password"
$env:MYSQL_HOST = "127.0.0.1"
$env:MYSQL_PORT = "3306"
```

`.env.example` is a variable template. The current Django settings do **not** load a `.env` file automatically, so configure these values in PowerShell, your IDE run profile or your deployment process.

Apply migrations, seed fictional data and start the server:

```powershell
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open `http://127.0.0.1:8000/accounts/login/` and select the matching role at sign-in.

## Fictional demo credentials

All demo accounts use the password `DemoPass!2026`. Use these only in development or a fictional demo environment.

| Role | Username |
|---|---|
| Administrator | `admin_demo` |
| Examiner | `examiner_ayesha` |
| Examiner | `examiner_bilal` |
| Candidate | `candidate_fatima` |
| Candidate | `candidate_hassan` |
| Candidate | `candidate_mariam` |
| Candidate | `candidate_omer` |
| Candidate | `candidate_sara` |

The seed command is safe to rerun. It refreshes these users and its six demonstration questions without deleting unrelated data.

## Tests

The test settings use in-memory SQLite so you do not need MySQL for the automated suite:

```powershell
python manage.py test --settings=exam_platform.settings_test
python manage.py test examinations --settings=exam_platform.settings_test
python manage.py makemigrations --check --dry-run --settings=exam_platform.settings_test
```

## Optional local proctoring agent

The web app works fully without a webcam, Bluetooth adapter or Gemini. During an in-progress attempt, a candidate can read and accept the monitoring notice. The browser then displays a one-time agent token. Run the lightweight demonstrator from the project folder:

```powershell
python -m proctor_agent --server http://127.0.0.1:8000 --token <one-time-token> --simulate
```

The simulated agent posts advisory test events only. Hardware dependencies remain optional in `proctor_agent/requirements-hardware.txt`. Evidence is stored in `PROCTOR_EVIDENCE_ROOT`, outside web-served media, and is removed with:

```powershell
python manage.py cleanup_proctor_evidence
```

Set `PROCTOR_EVIDENCE_RETENTION_DAYS` to control retention. Monitoring signals are advisory, never change scores, and require an owning examiner to accept or dismiss them with a note. RSSI, gaze, phone and face-related signals can be wrong because of lighting, camera angle, glasses, head coverings, device advertising behavior and noisy radio conditions.

## Deployment checklist

Deploy with environment variables supplied by the host, not committed files. Before a production deployment:

1. Set a strong `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false` and a specific `DJANGO_ALLOWED_HOSTS` value.
2. Provision a MySQL-compatible database and apply `python manage.py migrate`.
3. Configure HTTPS, static-file collection and an application process running `exam_platform.wsgi`.
4. Run the test suite and use only fictional demonstration data.

A hosting account, domain and production database are required to deploy. No provider credentials or deployment target are stored in this repository.

## Planned innovation and secondary features

- **5.2 fairness:** examiner-controlled Easy/Medium/Hard question counts and per-attempt random snapshots.
- **5.1 integrity:** optional local gaze, phone, screen and post-exam review signals, with consent, evidence minimization and local fallback.
- **5.5 participant-defined:** Bluetooth baseline detection with an OpenCV-derived distance threshold. RSSI is noisy and the signal remains advisory.
- **4.6 verifiable reports:** a QR code and unique verification identifier per issued PDF, showing only minimal public result information.

## Important privacy and integrity rules

- Deadlines are server-side and outages never extend an exam.
- Answer keys and private records are never public.
- Candidates can view only their own published results.
- Proctoring evidence is private, and flags are not proof of misconduct.
- `GEMINI_API_KEY`, database passwords and agent tokens belong only in environment variables.
