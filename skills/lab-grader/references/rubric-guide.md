# Building the rubric from an assignment

The rubric is the contract every grading agent follows, so it is built once by the
main session (good judgment, read the assignment fully) and approved by the TA before
any student is graded. Cheap agents then apply it mechanically.

## The TA's grading policy (fixed for every assignment)

- **80 points for the work itself**, split across the tasks **by difficulty and effort**.
  A one-command task with a short explanation weighs less than writing code or an analysis.
  Example: discovery scan 12, port scan 14, writing a program 28, comparison/analysis 26.
- **20 points for format and cleanliness**: one clean file, clear headings per task/section,
  readable screenshots (command + output visible), code shown as text or a clear screenshot,
  tables where asked, required report sections (intro, environment, conclusion...), name/ID present.
- **Bonus up to +10 for an exceptional report**, judged on format/presentation only:
  outstanding layout, very clean screenshots with captions, well-organised tables, professional look.
  Most students get 0. A few very good ones get +2 to +5, and +6 to +10 is rare.
  The bonus is never for "more theory". Maximum total = 110 (11/10).
- **Grades spread 6 to 10 before bonus (the curve).** `merge.py` stretches the rubric scores so the
  weakest *genuine attempt* in the class lands on 6.0, a full 100 stays 10.0, and everything in
  between scales linearly. Full marks are fine: if a student earned it, it's a 10.
- **Below 5 only for "too bad" submissions**: wrong assignment file, most tasks not done,
  invented results, empty or unreadable. These are decided by the Sonnet reviewer, keep their raw
  rubric score and are left out of the curve.
- **AI with proof costs points**: AI level `high` *and* `proven` takes `ai_penalty_high_proven`
  (default 10 points = 1 grade point) off the final. Everything else about AI is a note only.
- **Late submission**: `-1` grade (10 points) if up to 24 hours late, `-2` (20 points) if later,
  taken off the final grade. Ask the TA for the exact due date (Moodle: assignment page, "Due")
  and put it in `deadline`. Upload times come from the Moodle zip (file times), so no Moodle access is needed.
- **Maximum = Moodle's maximum grade. Always ask the TA, never assume** (it can be 10, 11 or
  something else). Put it in `moodle_max_grade`; `merge.py` caps every grade to it, and the bonus
  only helps up to that cap.
- **Final grade /10 = total/10 rounded UP to the next 0.5** (done by `merge.py`, not by agents).
- **Be kind.** Partial work earns partial credit. A missing screenshot but clear text output
  loses part of the evidence points, not the whole task. A wrong explanation loses the
  explanation points, not the command points. Small slips (typo in a heading, slightly
  blurry screenshot that is still readable) cost nothing or at most 1 point.
- **AI suspicion and copying never change the grade.** They are flagged for the TA.

## Steps

1. Read the assignment file fully (and any lab handout it references).
2. List every **deliverable** the assignment explicitly asks for: each task's command, output,
   recorded values, explanation, code, table, and each report section with its stated length.
3. Turn the assignment's own rules ("do not...", "must...", "keep...", "before you submit")
   into a **checklist with deductions**. Each check is attached to the item it belongs to,
   with a small, proportional deduction. Use the assignment's wording so the TA recognises it.
4. Assign the 80 points by difficulty, then the 20 format points, then define bonus criteria.
5. Add **global deductions** only for submission-level problems (wrong file type when one is
   required, e.g. `.docx` instead of PDF: 3 points from format; missing name/ID: 1 point;
   wrong assignment entirely: flag for TA rather than auto-zero).
6. Add **assignment-specific AI/fabrication signals**, i.e. things a student who really ran the lab
   would naturally have and an AI-written report would not. For example, results that contradict
   the screenshots, the assignment's example values reported with no screenshot behind them,
   explanations of states that never appear in their own output, or a "perfect" table with no
   matching evidence.
7. Fill `lab_allowlist` with functions/options the assignment *requires* but the lab text never
   names (e.g. "set a 3-second timeout" -> `settimeout`), so the beyond-the-lab check doesn't
   flag students for doing what was asked.
8. Write `rubric.json` (schema below) and a human-readable `rubric.md`, show the TA the table
   (item / points / main checks / deductions) and **wait for approval** before grading.

## rubric.json schema

```json
{
  "assignment": "ECOM5003 Assignment 1: Nmap and Python TCP comparison",
  "max_total": 110,
  "items": [
    {
      "id": "T3",
      "title": "Python port checker",
      "max": 28,
      "checks": [
        {"check": "Complete source code included (as text or clear screenshot)", "points": 8},
        {"check": "Fresh AF_INET/SOCK_STREAM socket per port, 3 s timeout, connect_ex, close", "points": 8},
        {"check": "Exceptions handled and recorded, not skipped", "points": 4},
        {"check": "Program output shown with return code per port", "points": 8}
      ],
      "deductions": [
        {"rule": "Labels every nonzero code CLOSED (assignment forbids this)", "points": 3},
        {"rule": "Different host/ports than Task 2", "points": 4}
      ]
    }
  ],
  "format": {"max": 20, "checks": [{"check": "Clear heading for each task", "points": 4}]},
  "bonus": {"max": 10, "criteria": ["Exceptionally clean, professional layout", "Captioned screenshots"]},
  "global_deductions": [{"id": "G1", "rule": "Submitted .docx instead of the required PDF", "points": 3}],
  "ai_signals_specific": ["Reports example host 192.168.56.20 but no screenshot shows it"],
  "curve": {"method": "stretch", "min_grade_10": 6, "max_grade_10": 10},
  "ai_penalty_high_proven": 10,
  "moodle_max_grade": 11,
  "deadline": "2026-10-24T00:00",
  "late_penalty": [{"max_hours": 24, "points": 10}, {"max_hours": null, "points": 20}],
  "student_id_regex": "(?<!\\d)(1\\d{8})(?!\\d)",
  "lab_allowlist": ["settimeout"],
  "kindness_notes": ["192.168.56.x and 10.0.2.x are VirtualBox defaults: never suspicious by themselves"]
}
```

`checks` points inside an item must sum to the item's `max`. The worker awards each check
fully, partly, or not at all, then subtracts that item's deductions (never below 0 for the item).
