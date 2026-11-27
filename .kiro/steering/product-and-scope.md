# Product and Scope

## Product
Secure Examination Management System for Technoverse 5.0 Web-e-Thon. A full-stack Django web app where institutions create, conduct, monitor and evaluate online exams.

## Roles
- **Administrator**: manages users, roles, permissions and platform operations.
- **Examiner**: creates and configures exams, manages questions and candidates, monitors attempts, grades, publishes results.
- **Candidate**: accesses assigned exams, answers and submits, views own published results.

## Constraints
- 10 hours of development, 1 to 3 people, 15-minute live demo, deployed app required.
- Everything must be demonstrable with fictional test data.
- The PDF is the source of truth. See `core-requirements.md`.
- This workspace also contains an unrelated Flutter project (AnubisQuesting). Ignore its Flutter, Firebase and Egyptian-theme rules here.

## Marking weights
Core 30, Secondary 15, Technical Quality 20, Open Innovation 15, UI/UX 20.

## Priority order
1. Core gaps and integrity (Tasks 1 to 6).
2. All eight secondary features (Tasks 7 to 12). All eight are expected.
3. UI/UX pass (Task 20). It carries 20 marks.
4. Innovation: 5.2 fairness (Task 4), then 5.1 and 5.5 proctoring (Tasks 13 to 19).
5. Hardening, README, demo script (Task 21).

Specs: `.kiro/specs/technoverse-exam-platform/` (requirements, design, tasks).

## Cut-line if time runs short
Drop in this order: identity check (Task 16), Gemini review (Task 18), screen-clip part of Task 15, Bluetooth (Task 17). Tasks 1 to 12 and 20 cover everything the PDF requires.

## Innovation selections
- 5.2: examiner sets Easy/Medium/Hard counts per exam. Each candidate gets a random draw, snapshotted in their attempt.
- 5.1: local agent (gaze, phone, screen) plus optional Gemini post-exam review.
- 5.5: Bluetooth earpieces for candidates wearing hijab or caps, scoped by webcam distance.
- 5.3 (partial): offline answer queue that never extends the server deadline.

## 4.6 choice
Unique QR code per issued report plus manual ID entry. Public verify page shows minimal data only.
