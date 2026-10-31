---
name: lab-grader
description: "Grade a folder of student lab/assignment submissions (PDF, DOCX, code, zip; Moodle download folders) against the assignment file. It builds a rubric for TA approval, grades /10 in 0.5 steps (spread 6-10, below 5 only for too-bad work, format bonus up to 11/10), detects AI-written reports, answers beyond what the lab taught, and copying/paraphrasing between students with detailed notes, and writes friendly Palestinian-Arabic feedback plus grades.csv / Moodle import CSV. Cost-efficient: local scripts do extraction/OCR/similarity, cheap Haiku agents grade in parallel batches, Sonnet reviews only flagged cases. Use this whenever the user (a TA/instructor) wants to grade, mark, evaluate, check or correct submissions, homework, labs, or assignments, or check for cheating, plagiarism or AI use in student work, even if they don't say \"grade\"."
---

# Lab grader

You are helping a teaching assistant grade a lab assignment. Three things matter to them,
in this order: **fair, kind grades they can defend**, **reliable flags for AI-written work
and copying**, and **low cost** (they are on a $20 plan). The design follows from that:

- Local scripts (free) do all extraction, OCR, metadata and cross-student comparison.
- **You (the main session) never read student submissions in bulk.** You build the rubric,
  dispatch agents, and merge results. Reading 40 reports yourself is the most expensive mistake.
- Haiku agents grade in parallel batches. Sonnet reviews only the cases that need judgment.
- **AI detection is a priority.** A free scan checks everyone; Sonnet writes a checkable note
  (evidence, where, a question to ask the student) for every flagged student. Answers that go
  beyond what the lab/assignment taught count as an AI signal. Only AI that is `high` **and
  proven** (the work itself isn't the student's) costs points; everything else is a note.
- **Grades spread 6–10** (the curve in `merge.py`); only "too bad" submissions (wrong file, most
  tasks missing, invented results, empty) can go below 5. Full marks are fine when earned.

`SKILL_DIR` below = the directory containing this file.

**Agent harness.** The scripts, rubric, briefs and output files are the same everywhere; only
the way agents are launched differs:

| Role | Claude Code (Agent tool) | Codex (`scripts/codex_agents.py`) |
|---|---|---|
| Graders (cheap, parallel batches) | `model: "haiku"` | newest Luna, default `gpt-6-luna` |
| Reviewers / AI-integrity (judgment) | `model: "sonnet"` | newest Terra, default `gpt-5.6-terra` |

In Codex, launch each phase with
`python3 SKILL_DIR/scripts/codex_agents.py "$WORK" worker|review|ai [--model <newer model>]`,
which runs one sandboxed `codex exec` per batch in parallel (write access limited to `$WORK`).
If neither subagents nor `codex exec` are available, run each batch yourself one at a time,
reading only that batch's `extracted/<pid>/` files.

## Phase 0: Locate inputs

Find in the user's folder: the **assignment file** (the spec, often a PDF at the top level),
the **submissions folder** (Moodle style: `<Student Name>_<participantId>_assignsubmission_file/`),
and any **lab handout / template code** the assignment builds on (needed so shared template
code is not counted as copying; ask if unclear). Use `WORK=<assignment folder>/grading` for all outputs.

## Phase 1: Extract + copy-check (free)

```bash
python3 SKILL_DIR/scripts/extract.py "<submissions_dir>" "$WORK"
python3 SKILL_DIR/scripts/similarity.py "$WORK" --template "<assignment.pdf>" "<lab handout.pdf>"
```

(`ai_scan.py` runs after the rubric exists, in Phase 5, because it reads the rubric's `lab_allowlist`.)

Run these without `python3 -I` (PyMuPDF lives in user site-packages). If the extractor warns
that tesseract is missing, tell the user that `sudo apt install tesseract-ocr` makes screenshot
reading free (they can run it with `! sudo apt install -y tesseract-ocr`), and continue. Workers
will look at images instead, which costs more.

Skim the printed manifest: page/char/image counts and auto flags (`NOT_PDF`, `LITTLE_TEXT`,
`META_SCRIPT_GENERATED`, archives needing manual extraction). Tell the user about anything
that blocks grading.

## Phase 2: Rubric (needs TA approval)

Read `references/rubric-guide.md`, then read the assignment fully. Write `$WORK/rubric.json`
and `$WORK/rubric.md` following the TA's fixed policy in that guide (80 work by difficulty /
20 format / bonus up to +10 / checklist deductions from the assignment's own rules / curve
6–10 / too-bad rule / AI penalty / `lab_allowlist` / round up to 0.5). Show the TA the rubric as a compact table and **stop for approval**. Grades built on
an unapproved rubric are wasted tokens. If `rubric.json` already exists and was approved
earlier, reuse it.

## Phase 3: Pilot on 5 (first run of a new assignment)

Before grading everyone, grade 5 students (random: `ls extracted | shuf -n 5`, or the TA's
choice) with the same worker setup as Phase 4, run `merge.py`, and show the TA a short table:
per-item points, total, /10, AI level, and the Arabic feedback. Ask what to change. Common
fixes are rebalancing item points, softer/harsher deductions, and what counts as bonus. Update
the rubric, re-grade the pilot if it changed materially, and only then do the full run.
Skip the pilot if the TA says the rubric is already calibrated.

## Phase 4: Parallel grading

Split the students into balanced batches of 6 (heavy and light submissions mixed so agents
finish together; exclude pilot students already graded):

```bash
python3 SKILL_DIR/scripts/plan.py "$WORK" batches --size 6 --exclude <pilot pids>
```

Spawn one worker per batch, **all in one message** so they run in parallel:

- `subagent_type: "general-purpose"`, `model: "haiku"`, `effort: "lower"`
- prompt = `references/worker-prompt.md` with `{WORK_DIR}`, `{SKILL_DIR}`, `{PID_LIST}` filled in

Workers write `$WORK/grades/<pid>.json`. When they return, check every pid has a file (re-run a
small batch for any missing ones).

## Phase 5: Sonnet review (only what needs it)

Build the case list (AI medium/high, unsure workers, script-generated/not-PDF/little-text
files, copy pairs, plus one calibration spot-check per batch that alternates between the
highest-scoring clean student and a random clean one, to catch a worker that graded too
hard or too soft):

```bash
python3 SKILL_DIR/scripts/plan.py "$WORK" review      # -> review_cases.json
```

Point the reviewer at `review_cases.json` with the pid list instead of pasting the reasons.
Spawn **one** agent: `model: "sonnet"`, prompt = `references/reviewer-prompt.md` filled in. If the
case list is above ~15, split it into two Sonnet agents in parallel. If the spot-checks show a
worker was systematically off, have the reviewer fix that whole batch.

## Phase 5b: AI & integrity review (Sonnet)

```bash
python3 SKILL_DIR/scripts/ai_scan.py "$WORK" --template "<assignment.pdf>" "<lab handout.pdf>"
python3 SKILL_DIR/scripts/plan.py "$WORK" ai          # -> ai_cases.json
```

`ai_scan.py` is free: placeholders, chat leftovers, raw Markdown, script-generated files, text
values contradicting the student's own screenshots, assignment example values, and code/tool
options beyond the lab (with how many classmates used each). It also writes `lab_reference.txt`.

Spawn Sonnet with `references/ai-reviewer-prompt.md` for the students in `ai_cases.json`
(about 8 per agent, in parallel; keep copy pairs in the same agent). It verifies each signal,
compares answers against the lab, decides `level` / `proven` / `too_bad`, and writes
`note_for_ta` + `ask_student`. This step decides who is too bad, so run it before the final merge.

## Phase 6: Merge and report

```bash
python3 SKILL_DIR/scripts/merge.py "$WORK" [--moodle-worksheet <worksheet.csv>] [--moodle-scale 10]
```

If the TA downloaded Moodle's offline grading worksheet ("Download grading worksheet"),
pass it so the import file matches Moodle exactly. Otherwise a minimal
`Identifier,Full name,Grade,Feedback comments` file is produced.

`merge.py` applies the curve (weakest genuine attempt → 6.0, 100 → 10.0, linear), keeps too-bad
students at their raw score, adds the bonus, subtracts the AI penalty for `high`+`proven`, and
honours TA overrides. `grades.csv` shows every step (`raw_100`, `curved_100`, `ai_penalty`, ...).

Tell the TA: where `grades.csv`, `moodle_import.csv` and `flags.md` are; the grade distribution;
how many AI/copy flags and the top ones in one line each; and any students above 10/10 (Moodle
needs the max raised or `unlimitedgrades` for those). Keep it short. The files hold the details.

## Re-runs and fixes

- TA wants a specific final grade for a student: add
  `"ta_adjustment": {"target_grade_10": 7.0, "reason": "TA decision"}` to `grades/<pid>.json`
  (or `{"points": X}` to add/subtract points) and re-run `merge.py`. Keep the rubric item scores as they are, so the
  breakdown stays honest and the CSV shows the adjustment was the TA's decision.
- TA disagrees with how a check was scored: edit that `grades/<pid>.json` (or re-spawn one Haiku worker for
  that pid) and re-run `merge.py`. Don't re-grade everyone.
- Late submission added: `extract.py ... --only <pid>`, re-run `similarity.py`, grade that pid, merge.

## Lessons from real runs

- Haiku workers tend to **zero whole tasks** for partial evidence (e.g. code shown only as
  REPL fragments) and to call evidence "missing" when it is in a thin cropped screenshot.
  The worker brief now forbids both, and the Sonnet calibration spot-checks exist to catch the rest.
- Most real AI evidence is **inconsistency**: numbers in the text that differ from the student's
  own screenshot, leftover placeholders (`[INSERT VERSION]`, `[ INSERT SCREENSHOT HERE ]`),
  the assignment's example IPs with screenshots showing another network, or printed code that
  doesn't match the program that ran. Script-generated metadata (python-docx/reportlab) is a
  strong pointer, not proof.
- Step-by-step trace assignments (assembly, debugger) can have 50+ screenshots. The extractor
  keeps up to `--max-images` (default 150) and flags `IMAGES_TRUNCATED` when it hits the cap;
  re-extract those students with a higher cap before grading, or the last pages (often the
  bonus) are silently missed.
- Check for **wrong-file submissions** (another lab's report, template left unedited): flag
  for the TA to contact the student rather than auto-zero.
- Copy-check false positives come from logos, stock cover images, PDF alpha masks and
  VirtualBox defaults (10.0.2.15, `vboxuser@`). The scripts already filter these.

## Cost rules of thumb

- Text is cheap, images are expensive. OCR first, open an image only when it decides points.
- Never paste a whole submission into your own context. Agents read files themselves.
- Haiku for checklists, Sonnet only for judgment calls, and you only for rubric/orchestration.
