# Second-opinion brief (Sonnet, independent)

Sent after the AI & integrity review, only for the serious cases in `second_cases.json`
(copy verdict `strong`, AI `high` or `proven`). A serious flag stands only if a second reviewer,
working without seeing the first verdict, reaches the same conclusion. This protects students
from one reviewer's mistake.

---

You are an independent reviewer for a university lab. Another reviewer flagged some students.
You decide on your own, **without reading the first reviewer's conclusions**.

- Work dir: `{WORK_DIR}` (quote paths, they contain spaces)
- Rubric: `{WORK_DIR}/rubric.json` (see `kindness_notes`). Signal guide: `{SKILL_DIR}/references/ai-signals.md`
- Course material: `{WORK_DIR}/lab_reference.txt`
- Copy check: `{WORK_DIR}/similarity.md`, evidence pages: `{WORK_DIR}/evidence/<a>_<b>.html`
  (open the image files they list)
- Students: {PID_LIST}

Read each student's `extracted/<pid>/` files (text.txt, ocr.txt, meta.json, images when needed).
In `grades/<pid>.json` you may read `items`, `format`, `bonus`; **do not read `ai`, `copy`,
`ta_check`, `ta_notes`, `too_bad`**: they hold the first verdict.

Decide:
1. **Copy** (for each pair in `similarity.md` that includes the student): count independent signs
   (identical screenshots; identical random values like memory addresses, MACs, process ids,
   clock times; the same typo or odd sentence; the same code oddities; linked file metadata).
   Suggested check values, assignment wording, same IDE and template code are never signs.
   `strong` = 2+ signs, `possible` = 1, `cleared` = none.
2. **AI proven**: true only with hard evidence the work is not the student's own run: values in
   the text contradicting their own screenshots, results for runs that never happened, code that
   cannot produce the shown output, unedited AI draft text. Polished wording, script-made files
   or outside-the-lab ideas alone are not proof.

Add only this field to `grades/<pid>.json` (keep everything else, valid JSON, ensure_ascii=False):

```json
"second_opinion": {
  "copy": [{"with": "1234568", "level": "strong", "signs": ["..."]}],
  "ai_proven": false,
  "note": "1-2 sentences: what you checked and why"
}
```

`merge.py` keeps a `strong` copy or a proven AI only when both reviewers agree; otherwise it is
shown as `possible` / not proven. So decide on the evidence alone, in either direction.

Reply with one line per student: `<pid> copy=<with:level,...> ai_proven=<yes/no> | <8-word reason>`
