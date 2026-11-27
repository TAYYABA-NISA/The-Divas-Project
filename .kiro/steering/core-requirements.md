# Technoverse Web-e-Thon Core Requirements

## Examination Setup & Access

### 3.1 Authentication & Authorization
- Support secure authentication for administrators, examiners and candidates with appropriate experience for each role
- Allow administrators to manage user accounts and role assignments
- **Enforce permissions on the backend, not merely by hiding interface elements**
- Ensure examiners and candidates access only authorized examinations, records and actions

### 3.2 Examination Management
- Allow examiners to create and configure examinations with:
  - Title, instructions, schedule, duration, total marks, and relevant settings
- Support examination lifecycle: draft → published → ongoing → completed
  - **Candidates must not access examinations before availability**
- Allow examiners to review examination details before publication and manage through appropriate interface

### 3.3 Question Management
- Provide reusable question bank with categories/topics and difficulty levels
- Support CRUD operations on questions
- Support question types:
  - Single-answer MCQs
  - Multiple-select questions
  - Written-response questions
  - Each with appropriate marking schemes
- Allow objective questions/answer choices to be randomized where applicable
  - **Preserve correct marking scheme and question assignment for active attempts**

### 3.4 Candidate Management
- Allow examiners to enroll candidates in examinations and view enrollment information
- Provide candidates with clear view of available, upcoming and completed examinations
  - Include relevant instructions and access status
- Restrict examination entry to eligible candidates and enforce availability window

## Examination Delivery & Results

### 3.5 Examination Interface
- Present in examination workspace: questions, marks, remaining time, navigation controls
- Distinguish answered, unanswered and marked-for-review questions
- **Automatically save answers during attempt**
- **Preserve previously saved progress and remaining time on refresh/return**
- Allow candidates to review progress and submit attempt
- Enforce time limit and finalize attempt at expiry using answers accepted within permitted period

### 3.6 Examination Monitoring
- Provide examiners with view of:
  - Active attempts and their progress
  - Relevant examination events/incidents
- Allow examiners to monitor examination status and communicate announcements to candidates
- Record and present relevant incidents for review
  - **Monitoring indicators must not be treated as conclusive evidence of misconduct**

### 3.7 Evaluation & Grading
- Automatically grade objective responses per configured marking scheme
  - Include rules for multiple-select answers
- Allow examiners to review and manually grade written responses
  - Validate against assigned marks
- Calculate total scores accurately and maintain consistent grading state
- **Examiners must review results before publication**

### 3.8 Results & Analytics
- Allow examiners to publish results in controlled manner
- **Candidates view only their own published results unless authorized otherwise**
- Present meaningful examination-level performance summaries and candidate-level scores using actual submission data
- Retain completed attempts and results for later review by authorized users

---

# Sections 4 to 8 (from the official PDF: Web-e-Thon Problem Statement)

Source of truth: `Web-e-Thon Problem Statement.pdf` (Technoverse 5.0, 7 pages). Development time: 10 hours. Team size: 1-3. Evaluation: 15-minute live demo.

## 04 Secondary Features
All eight are expected. Marks go to working functionality, usefulness and integration.

- **4.1 Network-Aware Interface**: detect and communicate connectivity problems and answer saving/synchronization status. Clear feedback when the connection is unstable or unavailable.
- **4.2 PDF Report Generation**: downloadable, readable PDF reports from actual exam and candidate performance data, with appropriate access restrictions.
- **4.3 Examination Sandbox**: examiners preview and experience an exam as a candidate. Sandbox attempts must not affect real submissions, results or statistics.
- **4.4 Bulk Data Import**: import candidate records and questions from CSV or JSON. Validate and communicate import errors clearly.
- **4.5 Question Analytics**: insights per question, such as frequently skipped questions, commonly incorrect responses or observed difficulty.
- **4.6 Verifiable Reports**: a mechanism to verify the authenticity of an issued result report, such as a unique verification identifier or QR code, **without exposing unnecessary candidate information**. (Our choice: unique QR code plus manual ID entry.)
- **4.7 Customizable Examination Workspace**: candidates customize layout or viewing preferences, and the preferences are retained.
- **4.8 Digital Scratchpad**: a dedicated space for rough work, usable within the exam workflow.

## 05 Open Innovation Challenges
Implement at least one. Quality over quantity. The same implementation is not rewarded twice.

- **5.1 Integrity in the AI Era**: improve integrity without unnecessarily compromising privacy or usability.
- **5.2 Fairness of Randomized Examinations**: improve fairness while preserving meaningful variation between papers.
- **5.3 Failure-Resilient Examinations**: reduce the impact of outages and failures without granting extra time or unfair advantage.
- **5.4 Trust & Dispute Resolution**: fair, transparent, accountable dispute handling.
- **5.5 Participant-Defined Challenge**: explain why the problem matters, who it affects and how the solution addresses it.

Our selection: 5.1 (gaze, phone, screen, optional Gemini review), 5.2 (examiner-set difficulty ratio), 5.5 (Bluetooth earpieces for candidates wearing hijab or caps, scoped by webcam-estimated distance), and partly 5.3 (offline answer queue).

## 06 Technical Requirements & Constraints
- **Security & privacy**: server-side authorization. Protect credentials, answer keys, personal information and exam records. No private data through public endpoints or reports.
- **Data integrity**: enforce timing independently of the candidate's device clock. Prevent duplicate submissions and inconsistent grading. Preserve assigned questions and marking scheme for active attempts.
- **Validation & reliability**: validate on frontend and backend. Handle invalid data, interrupted requests, refreshes and repeated actions. Communicate failures and saving status clearly.
- **Architecture & maintainability**: appropriate database design, separation of responsibilities, maintainable code. Be ready to explain technology choices.
- **Technical freedom & fairness**: AI-assisted coding allowed. AI integration is optional. **No required feature may depend on paid APIs, paid keys, proprietary datasets, specialized hardware or services requiring billing information.** Simulated services or local alternatives are acceptable.

## 07 Submission Requirements
- Git repository with source code and version history, plus a deployed, functional web application.
- Concise README: setup instructions, test credentials for each role, dependencies, description of implemented innovation challenge(s).
- Demonstrable with fictional or test data. Ready for the 15-minute evaluation.
- No commits, pushes, builds or deployments after the deadline. No timestamp manipulation.

## 08 Evaluation Criteria (100 marks)
| Category | Marks |
|---|---|
| Core Functionality | 30 |
| Secondary Features | 15 |
| Technical Quality & Reliability | 20 |
| Open Innovation Challenges | 15 |
| UI/UX & Product Design | 20 |

- UI: consistent, accessible, clear navigation and hierarchy, responsive, intuitive. Avoid generic, template-like or unrefined AI-generated interfaces.
- Functionality over quantity. Partial marks for incomplete requirements. Non-functional placeholders get no full credit.
- Judges may test common scenarios and ask for design explanations.
