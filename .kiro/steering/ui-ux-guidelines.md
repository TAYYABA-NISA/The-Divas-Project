# UI/UX Guidelines

UI/UX and product design carry 20 marks. Judges penalize generic, template-like or unrefined interfaces.

## Structure
- Consistent navigation per role (admin, examiner, candidate). Show the user's role and current location.
- Clear information hierarchy. One primary action per screen.
- Discoverable features: every secondary feature (sandbox, import, reports, analytics, preferences, scratchpad) reachable from a visible menu or page.

## Exam workspace
- Show question, marks, remaining time and navigation together.
- Distinguish answered, unanswered and marked-for-review with color and a text or icon label (never color alone).
- Always show save status: Saved, Saving, Offline (will retry), Unstable.
- Show the scratchpad and preferences without leaving the exam.

## Accessibility
- Keyboard-operable everywhere, visible focus, logical tab order.
- Labels on all form fields, ARIA live region for timer warnings and save status.
- Sufficient contrast. Provide a high-contrast option and adjustable font size.
- Do not rely on color alone.

## Responsive
- Layouts work from phone width to desktop. Test at mobile width.

## States
- Provide empty, loading, error and success states. Error messages say what happened and what to do.
- Confirm destructive or irreversible actions (submit exam, publish results).

## Visual
- A single consistent design system: spacing scale, type scale, color tokens in one stylesheet in `static/`.
- Use charts only where they help (score distribution, per-question stats).
- Proctoring UI uses neutral wording: "flagged for review".
