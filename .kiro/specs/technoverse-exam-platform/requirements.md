# Requirements: Technoverse 5.0 Web-e-Thon, Secure Examination Management System

Source of truth: `Web-e-Thon Problem Statement.pdf` (7 pages). Constraints: 10 hours, 1-3 people, 15-minute live demo, deployed app.

## Introduction
Online exams face problems of academic integrity, fairness, network reliability and managing many candidates. This system is a full-stack web application for creating, conducting, monitoring and evaluating online exams. It implements all core requirements (3.1-3.8), all eight secondary features (4.1-4.8), and innovation challenges 5.1, 5.2, 5.5 and part of 5.3.

## Roles
- **Administrator**: manages users, roles, access permissions and platform operations.
- **Examiner**: creates and configures exams, manages questions and candidates, monitors attempts, evaluates submissions and publishes results.
- **Candidate**: accesses assigned exams, completes and submits answers, views published results.

## Glossary
- **Attempt**: one candidate's sitting of one exam. **Sandbox attempt**: an examiner's preview attempt.
- **Blueprint**: examiner-set count of Easy/Medium/Hard questions for an exam.
- **Agent**: local Python proctoring program on the candidate's PC.
- **Flag**: an advisory proctoring event for human review.
- **Verified report**: an issued PDF with a unique public ID and QR code.

---

## Core Requirements

### Requirement 1 (PDF 3.1): Authentication and authorization
**User story:** As an administrator, I want to manage accounts and roles, so that each person has the right access.
1. THE System SHALL support secure sign-in for administrators, examiners and candidates, each with a role-appropriate experience.
2. THE System SHALL let administrators create, edit, deactivate users and change roles.
3. THE System SHALL enforce all permissions on the backend, not only by hiding interface elements.
4. THE System SHALL ensure examiners and candidates access only the exams, records and actions they are authorized for.
5. THE System SHALL prevent removal of the last administrator.

### Requirement 2 (PDF 3.2): Examination management
1. THE System SHALL let examiners create and configure exams with title, instructions, schedule, duration, total marks and settings.
2. THE System SHALL support the lifecycle draft, published, ongoing, completed.
3. THE System SHALL block candidate access before the exam is available.
4. THE System SHALL let examiners review exam details before publication and manage exams through an interface.

### Requirement 3 (PDF 3.3): Question management
1. THE System SHALL provide a reusable question bank with categories or topics and difficulty levels (Easy, Medium, Hard).
2. THE System SHALL allow questions to be created, edited and assigned to exams.
3. THE System SHALL support single-answer MCQ, multiple-select and written-response questions, each with an appropriate marking scheme.
4. WHERE randomization is enabled, THE System SHALL randomize questions or choices while preserving the correct marking scheme and question assignment for an active attempt.

### Requirement 4 (PDF 3.4): Candidate management
1. THE System SHALL let examiners enroll candidates and view enrollment information.
2. THE System SHALL show candidates their available, upcoming and completed exams, with instructions and access status.
3. THE System SHALL restrict entry to eligible candidates and enforce the availability window.

### Requirement 5 (PDF 3.5): Examination interface
1. THE System SHALL present questions, marks, remaining time and navigation in an accessible workspace.
2. THE System SHALL distinguish answered, unanswered and marked-for-review questions.
3. THE System SHALL autosave answers during an attempt.
4. WHEN a candidate refreshes or returns, THE System SHALL restore saved progress and remaining time.
5. THE System SHALL let candidates review progress and submit.
6. WHEN time expires, THE System SHALL finalize the attempt using answers accepted within the permitted period.

### Requirement 6 (PDF 3.6): Examination monitoring
1. THE System SHALL show examiners active attempts, their progress and relevant events or incidents.
2. THE System SHALL let examiners monitor exam status and post announcements that candidates see during the exam.
3. THE System SHALL record incidents and present them for review.
4. THE System SHALL state that monitoring indicators are not conclusive evidence of misconduct.

### Requirement 7 (PDF 3.7): Evaluation and grading
1. THE System SHALL auto-grade objective responses per the marking scheme, including multiple-select rules.
2. THE System SHALL let examiners grade written responses, validating marks against the assigned marks.
3. THE System SHALL compute total scores accurately and keep grading state consistent.
4. THE System SHALL let examiners review results before publication.

### Requirement 8 (PDF 3.8): Results and analytics
1. THE System SHALL let examiners publish results in a controlled manner.
2. THE System SHALL show a candidate only their own published results unless authorized otherwise.
3. THE System SHALL present exam-level summaries and candidate-level scores from actual submission data.
4. THE System SHALL retain completed attempts and results for later review by authorized users.

---

## Secondary Features (all eight expected)

### Requirement 9 (PDF 4.1): Network-aware interface
1. THE System SHALL detect connectivity problems and show save or sync status (Saved, Saving, Offline will retry, Unstable).
2. WHILE offline, THE System SHALL queue unsent answers locally and resync in order on reconnect.
3. THE System SHALL accept a queued answer only if saved before the server deadline.

### Requirement 10 (PDF 4.2): PDF report generation
1. THE System SHALL generate downloadable, readable PDF reports from actual exam and performance data.
2. THE System SHALL restrict candidate reports to the candidate's own published results and exam reports to the owning examiner.

### Requirement 11 (PDF 4.3): Examination sandbox
1. THE System SHALL let examiners preview and take an exam as a candidate.
2. THE System SHALL exclude sandbox attempts from real submissions, results, monitoring, reports and statistics.

### Requirement 12 (PDF 4.4): Bulk data import
1. THE System SHALL import candidates and questions from CSV or JSON.
2. THE System SHALL validate the data, show row-level errors in a preview, and commit atomically.

### Requirement 13 (PDF 4.5): Question analytics
1. THE System SHALL show per question: skip rate, correct rate, most-chosen wrong option, and observed versus labelled difficulty.

### Requirement 14 (PDF 4.6): Verifiable reports
1. THE System SHALL give each issued report a unique unguessable verification ID and a QR code on the PDF.
2. THE System SHALL provide a public verification page and a manual ID entry form.
3. THE verification page SHALL show only: authentic, revoked or superseded status, exam title, issue date, masked candidate name, score and total.
4. THE verification page SHALL NOT show email, identifiers, answers or other candidates.
5. WHEN a result is regraded, THE System SHALL mark the earlier report superseded.
6. THE verification endpoint SHALL be rate-limited.

### Requirement 15 (PDF 4.7): Customizable workspace
1. THE System SHALL let candidates set layout and viewing preferences (font size, theme or high contrast, palette position, density).
2. THE System SHALL persist the preferences and apply them in every attempt.

### Requirement 16 (PDF 4.8): Digital scratchpad
1. THE System SHALL provide a scratchpad inside the exam workspace, autosaved per attempt.
2. THE scratchpad SHALL be visible only to its candidate and SHALL NOT be graded.

---

## Open Innovation Challenges

### Requirement 17 (PDF 5.2): Fairness of randomized examinations
1. THE System SHALL let an examiner set Easy, Medium and Hard question counts per exam (and optional category filter).
2. THE System SHALL draw each candidate's questions randomly from the examiner's bank according to the counts, and snapshot them into the attempt.
3. THE System SHALL store the random seed per attempt and return the same snapshot on reopen.
4. IF the bank cannot satisfy the counts, THEN THE System SHALL reject publication with a clear error.

### Requirement 18 (PDF 5.1): Integrity in the AI era
1. THE System SHALL require candidate consent and show a monitoring notice before the agent starts.
2. THE Agent SHALL detect prolonged off-screen gaze, no face, multiple faces and phones, and capture short evidence clips (screen and webcam) around flags.
3. WHERE a face photo is enrolled, THE Agent SHALL compare the live face at start and raise a flag on mismatch without blocking the exam.
4. THE System SHALL authenticate the agent with a per-attempt token valid only while the attempt is in progress.
5. WHERE a Gemini key is configured, THE System SHALL summarize flagged evidence after the exam; otherwise it SHALL produce a local rule-based summary.
6. THE System SHALL let examiners accept or dismiss each flag with a required note.
7. THE System SHALL NOT change any score because of a flag.
8. THE web application SHALL work fully without the agent, and the agent SHALL offer a simulated mode.

### Requirement 19 (PDF 5.5): Bluetooth earpieces (participant-defined)
**Problem:** Candidates wearing hijabs or caps can hide wireless earpieces from camera checks. This affects fair invigilation of those candidates and everyone else.
1. THE Agent SHALL run a baseline Bluetooth scan before the exam and upload hashed device identifiers.
2. DURING the exam, THE Agent SHALL flag devices not in the baseline that are within a range derived from the OpenCV candidate-to-screen distance.
3. THE System SHALL document that RSSI is noisy and some earbuds do not advertise, and SHALL treat the result as a hint only.
4. THE Agent SHALL offer a simulated Bluetooth mode.

### Requirement 20 (PDF 5.3, partial): Failure resilience
1. THE System SHALL preserve saved answers and remaining time across refresh and short outages.
2. THE System SHALL NOT extend the deadline because of an outage.

---

## Technical Requirements (PDF Section 6)

### Requirement 21: Security and privacy
1. THE System SHALL enforce server-side authorization and protect credentials, answer keys, personal information and exam records.
2. THE System SHALL NOT expose private data via public endpoints or reports.

### Requirement 22: Data integrity
1. THE System SHALL enforce timing using server time, independent of the device clock.
2. THE System SHALL prevent duplicate submissions and inconsistent grading, and preserve assigned questions and marking scheme for active attempts.

### Requirement 23: Validation and reliability
1. THE System SHALL validate input on both frontend and backend.
2. THE System SHALL handle invalid data, interrupted requests, refreshes and repeated actions, and communicate failures and saving status clearly.

### Requirement 24: Architecture and maintainability
1. THE System SHALL use a sound relational design, separate views from services, and keep code maintainable.

### Requirement 25: Technical freedom and fairness
1. NO required feature SHALL depend on paid APIs, paid keys, proprietary datasets, specialized hardware or billing-required services.
2. AI integration SHALL be optional, with local alternatives or simulation.

## Submission and Evaluation (PDF Sections 7 and 8)

### Requirement 26: Submission
1. THE project SHALL include a Git repository with version history and a deployed, functional app.
2. THE README SHALL include setup instructions, test credentials for each role, dependencies, and a description of the implemented innovation challenges and the 4.6 design.
3. THE app SHALL be demonstrable with fictional data in 15 minutes.
4. NO commits, pushes, builds or deployments SHALL occur after the deadline.

### Requirement 27: UI/UX (20 marks)
1. THE System SHALL provide consistent, accessible, responsive navigation and clear hierarchy, avoiding generic template-like design.
2. THE System SHALL provide empty, loading, error and success states.

### Marks
Core Functionality 30, Secondary Features 15, Technical Quality and Reliability 20, Open Innovation 15, UI/UX and Product Design 20.

---

## Traceability

| PDF item | Requirement (short) | Requirement # | Task |
|---|---|---|---|
| 3.1 | Auth per role, admin manages users/roles, backend permissions | 1 | 2 |
| 3.2 | Exam config, lifecycle, review before publish | 2 | exists; audited in 3 |
| 3.3 | Question bank, types, randomization preserved | 3 | exists; extended in 4 |
| 3.4 | Enrollment, candidate view, availability window | 4 | exists; audited in 3 |
| 3.5 | Workspace, autosave, refresh-safe, timed finalization | 5 | exists; audited in 3, extended in 8, 9 |
| 3.6 | Monitoring, announcements, incidents | 6 | 5 |
| 3.7 | Grading | 7 | 6 |
| 3.8 | Results and analytics | 8 | 6, 7 |
| 4.1 | Network-aware interface | 9 | 8 |
| 4.2 | PDF reports | 10 | 12 |
| 4.3 | Sandbox | 11 | 11 |
| 4.4 | Bulk import | 12 | 10 |
| 4.5 | Question analytics | 13 | 7 |
| 4.6 | Verifiable reports | 14 | 12 |
| 4.7 | Customizable workspace | 15 | 9 |
| 4.8 | Scratchpad | 16 | 9 |
| 5.2 | Fairness | 17 | 4 |
| 5.1 | Integrity | 18 | 13-16, 18, 19 |
| 5.5 | Bluetooth earpieces | 19 | 17 |
| 5.3 | Failure resilience (partial) | 20 | 8 |
| 6 | Technical requirements | 21-25 | 3, 18, 21 |
| 7 | Submission | 26 | 1, 21 |
| 8 | UI/UX | 27 | 20 |
