# Proctoring and Privacy

## Principles
- Consent first. The candidate accepts a monitoring notice before the agent starts. The notice lists what is collected.
- Collect the minimum. Keep short evidence clips around flagged events, not full recordings.
- Flags never change scores or results. They are advisory.
- Examiners accept or dismiss each flag with a required note. The decision is stored with user and timestamp.
- The UI always shows that indicators are not conclusive evidence of misconduct.

## Data handling
- Bluetooth device addresses are hashed before upload.
- Evidence files are stored privately (not in static or media served publicly) and served only to the owning examiner.
- A retention setting controls how long evidence is kept.
- Agent tokens are per attempt, stored hashed, and valid only while the attempt is IN_PROGRESS.
- Do not log raw biometric data, face images or tokens.
- Candidates cannot read their own proctor events.

## Detectors
- Gaze: MediaPipe Face Mesh. Flag only after a configurable time away, debounced. Also no face and multiple faces.
- Phone: YOLOv8n `cell phone` class over several consecutive frames with a minimum confidence.
- Identity: lightweight face comparison against an enrolled photo. A mismatch only creates an event.
- Screen: `mss` ring buffer. Save a short clip only when an event fires.
- Bluetooth: `bleak` baseline scan before the exam. Flag only new devices that appear during the exam. The OpenCV distance sets an RSSI threshold with a log-distance path-loss model.

## Documented limits (state these in the README and UI)
- RSSI is noisy and not an exact distance.
- Many earbuds do not advertise in their case or while connected.
- Lighting, glasses, head coverings and camera angle can cause false gaze or face flags.
- Flags are hints for human review.

## Gemini
- Optional, post-exam only, sends flagged evidence only. Ask for observed behaviour, confidence and innocent explanations as structured JSON.
- Missing key or failure produces a local rule-based summary.
- Key from `GEMINI_API_KEY` in the environment.

## Fairness and respect
- Do not target any group. The Bluetooth feature applies to all candidates equally.
- Keep wording neutral and respectful in the UI and reports.
