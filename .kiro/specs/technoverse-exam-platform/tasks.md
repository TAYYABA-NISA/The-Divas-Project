# Implementation Plan: Technoverse Secure Examination Management System

Priority order for the 10-hour limit. Tasks 1 to 12 and 20 cover everything the PDF requires. Requirement numbers refer to `requirements.md`.

**Cut-line if time runs short (drop in this order):** Task 16, Task 18, the screen-clip part of Task 15, then Task 17.

- [ ] 1. Foundation, spec artifacts and deployment baseline
  - Complete `.kiro` steering, specs and hooks. Split requirements into web and `proctor_agent/` files (web: Django, mysqlclient, reportlab, qrcode or segno, google-genai; agent: opencv-python, mediapipe, ultralytics, mss, bleak, numpy, requests).
  - Choose a deployment target with no billing requirement and deploy a stub.
  - Add a seed command: 1 admin, 2 examiners, 5 candidates, sample questions across difficulties.
  - Start the README with setup steps and test credentials per role.
  - Tests: existing suite passes. Demo: deployed site loads and each role can sign in.
  - _Requirements: 24, 26_

- [ ] 2. Admin user and role management (3.1)
  - Admin-only views with `role_required`: create, edit, deactivate, change roles. Block removing the last admin.
  - Tests: 403 for non-admins on every admin URL; role changes apply immediately.
  - Demo: admin promotes a candidate to examiner.
  - _Requirements: 1_

- [x] 3. Core audit and data integrity (3.2, 3.4, 3.5, Section 6)
  - Confirm all deadlines use server time. Prevent duplicate submissions. Confirm refresh restores answers and remaining time. Confirm the candidate dashboard shows available, upcoming and completed exams with access status. Fix gaps.
  - Tests: late saves rejected, double submit idempotent, entry before the window blocked.
  - Demo: refresh mid-exam, answers and timer intact.
  - _Requirements: 2, 4, 5, 22, 23_

- [ ] 4. Difficulty-ratio exam generation (3.3, 5.2)
  - Add `ExamBlueprint`. Draw per attempt with a stored seed and snapshot into `AttemptQuestion`. Validate pool size at publish. Keep choice shuffling. Blueprint form on the exam detail page; manual assignment stays. Total marks from the drawn set. Explain the approach in the README.
  - Tests: exact per-difficulty counts, different draws per candidate, same snapshot on reopen, short pool rejected.
  - Demo: two candidates get the same ratio with different questions.
  - _Requirements: 3, 17_

- [ ] 5. Monitoring and announcements (3.6)
  - Monitor page with progress and recent events. Announcement form creating ANNOUNCEMENT events, shown to candidates via a polled endpoint. Manual incident logging. Show the "not conclusive evidence" notice.
  - Tests: ownership checks; candidates see only announcements for their own exam.
  - Demo: announcement appears in a live attempt.
  - _Requirements: 6_

- [ ] 6. Grading, review and publication (3.7, 3.8)
  - Written-response grading queue validated against assigned marks. One service function recomputes `Attempt.total_score`. Review page. Publish blocked while ungraded answers remain. Candidate "my results" page. Check multiple-select marking rules. Retain completed attempts.
  - Tests: marks over the limit rejected; no cross-candidate or unpublished result readable; consistent after regrade.
  - Demo: grade, publish, candidate sees only their score.
  - _Requirements: 7, 8_

- [ ] 7. Analytics and question analytics (3.8, 4.5)
  - Average, median, highest, lowest, distribution. Per question: skip rate, correct rate, most-chosen wrong option, observed versus labelled difficulty. CSV export. Aggregation in a service function.
  - Tests: values match a fixture dataset; sandbox attempts excluded.
  - Demo: analytics page for a completed exam.
  - _Requirements: 8, 13_

- [ ] 8. Network-aware interface and resilience (4.1, 5.3)
  - Online and offline events plus heartbeat. Status: Saved, Saving, Offline (will retry), Unstable. Queue unsent answers in localStorage and resync in order. Server accepts queued answers only before the deadline; offline time never extends it.
  - Tests: queue resends in order; late answers rejected.
  - Demo: disable network mid-exam, answer, reconnect, answers sync.
  - _Requirements: 9, 20_

- [ ] 9. Customizable workspace and scratchpad (4.7, 4.8)
  - Per-user preferences (font size, theme or high contrast, palette position, density), stored server-side and applied on every attempt. Scratchpad panel autosaved per attempt, visible only to its candidate, never graded.
  - Tests: preferences persist; scratchpad isolated per candidate.
  - Demo: change layout, refresh, it stays; scratchpad text survives refresh.
  - _Requirements: 15, 16_

- [ ] 10. Bulk import (4.4)
  - Upload CSV or JSON for candidates and questions. Validate, preview with row-level errors, commit atomically. Downloadable templates. Handle size limits, duplicates, bad encoding.
  - Tests: valid and invalid files, partial errors, atomic rollback.
  - Demo: import 20 questions and 10 candidates with one bad row clearly reported.
  - _Requirements: 12_

- [ ] 11. Examination sandbox (4.3)
  - Add `Attempt.is_sandbox`. Make the unique constraint conditional on non-sandbox. Exempt sandbox from enrollment and window checks. Exclude sandbox from every result, analytics, monitoring and report query via a default manager.
  - Tests: no sandbox data in any statistic; no real candidate affected.
  - Demo: examiner takes the exam as a candidate; analytics unchanged.
  - _Requirements: 11_

- [ ] 12. PDF reports and verifiable reports (4.2, 4.6)
  - ReportLab PDFs and qrcode or segno. Candidate result report (own published results) and examiner exam summary (own exams). `VerifiedReport` and public rate-limited `/verify/<public_id>/` page with manual ID entry. Regrade supersedes the old report.
  - Tests: download access control; verify page shows only allowed fields; unknown, revoked and superseded IDs; altered data hash fails; rate limiting.
  - Demo: download a PDF, scan the QR with a phone, see the authenticity page.
  - _Requirements: 10, 14, 21_

- [ ] 13. Proctoring backend, consent and agent API (5.1)
  - `proctoring` app: `ProctorSession`, `ProctorEvent`, `ProctorClip`, `DeviceBaseline`, `AIReview`. Consent page and monitoring notice. Per-attempt tokens stored hashed, valid only while IN_PROGRESS. Private evidence storage served only to the owning examiner. Retention setting.
  - Tests: bad or cross-attempt tokens rejected; candidate cannot read their own events.
  - Demo: accept consent, post a test event with curl.
  - _Requirements: 18_

- [ ] 14. Agent, gaze and distance (5.1)
  - `python -m proctor_agent --token ... --server ...`. MediaPipe Face Mesh for iris and head pose. Flag after N seconds, debounced. No-face and multiple-face events. Pinhole distance estimate with one-time calibration. Simulated mode with a sample video.
  - Tests: gaze-duration state machine and distance function with synthetic landmarks.
  - Demo: look away, GAZE_AWAY event shows in the monitor.
  - _Requirements: 18, 25_

- [ ] 15. Phone detection and screen capture (5.1)
  - YOLOv8n `cell phone` class over several consecutive frames and a minimum confidence. `mss` ring buffer saved as a clip on event. Upload size caps.
  - Tests: consecutive-frame filter and ring buffer.
  - Demo: hold up a phone, see the event with a clip.
  - _Requirements: 18_

- [ ] 16. Identity check (5.1, optional)
  - Profile photo upload, lightweight embedding comparison. Mismatch creates an ID_MISMATCH event and never blocks the exam.
  - Tests: same-person and different-person fixtures; mismatch only creates an event.
  - Demo: start with a different face, see a flagged event.
  - _Requirements: 18_

- [ ] 17. Bluetooth earpiece detection (5.5)
  - Baseline scan (about 20 s, bleak) uploaded as `DeviceBaseline`; periodic scans flag devices not in the baseline. The OpenCV distance sets an RSSI threshold via `rssi = tx_power - 10*n*log10(d)`, calibrated on baseline devices where possible. Prefer audio-like devices for higher severity. Hash device addresses. Document limits. Simulated mode with a mocked scanner.
  - Tests: baseline diff and distance-to-RSSI with a mocked scanner.
  - Demo: turn on earbuds mid-exam, BT_DEVICE_NEARBY appears; baseline devices don't trigger.
  - _Requirements: 19_

- [ ] 18. Gemini review with local fallback (5.1, optional)
  - Management command plus button. Send only flagged evidence to Gemini, asking for observed behaviour, confidence and innocent explanations as structured JSON. `GEMINI_API_KEY` from env. Missing key or failure produces a rule-based local summary. Rate-limit handling, retries, media downscaling. Nothing else depends on this task.
  - Tests: mocked client, JSON parsing, fallback and failure paths, no review without evidence.
  - Demo: run the review with and without a key.
  - _Requirements: 18, 25_

- [ ] 19. Examiner flag review dashboard (3.6, 5.1)
  - Per-candidate timeline with events, clips, AI summary. Accept or dismiss with a required note stored as `ReviewDecision` (user, timestamp). Always show the advisory notice. No automatic score change.
  - Tests: only the owning examiner can view and decide; decisions audited.
  - Demo: full flow from flagged attempt to examiner decision.
  - _Requirements: 6, 18_

- [ ] 20. UI/UX and accessibility pass (Section 8)
  - Consistent role-based navigation, hierarchy, responsive layouts, keyboard navigation, visible focus, ARIA labels, contrast, empty and error states; charts only where useful.
  - Tests: manual checks at mobile width, keyboard-only exam workspace, contrast check.
  - Demo: walk through each role on a phone-sized screen.
  - _Requirements: 27_

- [ ] 21. Hardening, README and demo script
  - Permission sweep over every URL. Complete README (setup, test credentials per role, dependencies, description of challenges 5.1, 5.2, 5.5 and the 4.6 design). Fictional demo data. Agent setup and simulated mode instructions. Timed 15-minute demo script. Final deployment check. No commits after the deadline.
  - Tests: full suite plus a manual end-to-end checklist.
  - Demo: the complete 15-minute flow.
  - _Requirements: 21, 22, 23, 26_

## Assumptions
- The verify page shows score and masked name (can be reduced to authentic, exam and date only).
- The deployed demo uses the agent's simulated mode; the live hardware demo runs from a laptop.
- Gemini's free tier needs a key but not billing; the app is fully functional without it.
