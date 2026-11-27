# Security and Data Integrity

## Authorization
- Enforce permissions on the backend. Hiding a button is not a permission check.
- Examiners reach only their own exams, questions and candidates' attempts for those exams. Candidates reach only their own enrollments, attempts and published results. Admin-only views require the admin role.
- Return 403 or 404 for unauthorized access. Add a test for each new view.

## Timing and attempts
- All deadlines use server time. Never trust the device clock.
- Offline time never extends a deadline. Queued answers are accepted only if saved before the server deadline.
- Prevent duplicate submissions. Finalize and answer-save operations must be idempotent and transactional.
- Snapshot questions, marks and choices into the attempt, so later edits do not change an active attempt.

## Data exposure
- Never send answer keys (`is_correct`) to the client during an attempt.
- No private data on public endpoints. The `/verify/<public_id>/` page shows only: authentic/revoked/superseded, exam title, issue date, masked candidate name, score and total.
- Candidates read only their own published results.
- Sandbox attempts are excluded from every real result, analytic and report.

## Validation and reliability
- Validate on the frontend and backend. The backend is authoritative.
- Handle invalid data, interrupted requests, refreshes and repeated actions. Show clear failure and saving status.

## Secrets
- Secrets only in environment variables. Keep `.env.example` updated. Never log tokens or keys. Store agent tokens hashed.

## No paid or hardware dependency for required features
- Gemini is optional. Missing key or API failure falls back to a local rule-based summary.
- Webcam and Bluetooth features are optional extras. The agent has a simulated mode. The web app works fully without the agent.

## Proctoring wording
- Monitoring indicators are advisory, never conclusive. Use wording like "flagged for review", not "cheating detected".
