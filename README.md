# lab-grader: grade lab assignments with Claude Code or Codex

An agent skill for teaching assistants. Point it at a folder of student submissions (a Moodle
download, or any folder with one sub-folder per student) and the assignment file, and it:

- **builds a rubric from the assignment** and waits for your approval before grading anyone
- **runs a 5-student pilot** so you can calibrate before the full run
- **grades everyone in parallel** with cheap agents, then has a stronger model review only the
  cases that need judgment (flags, low confidence, plus calibration spot-checks)
- **detects AI-written reports** with checkable evidence: leftover placeholders and chat text,
  results that contradict the student's own screenshots, script-generated files, and
  **code or ideas beyond what the lab taught**, with a question to ask the student
- **detects copying between students**: identical screenshots, shared MAC addresses / shell
  prompts, matching code, and paraphrased (reworded) reports
- **writes friendly feedback** per student (Palestinian colloquial Arabic by default)
- outputs `grades.csv`, a **Moodle import CSV**, and `flags.md` (everything you should look at)

Grading policy (editable in the rubric): 80 points of work split by task difficulty, 20 points
of format, up to +10 bonus for an exceptional report (max 11/10). Grades are curved to spread
**6–10**; only "too bad" submissions (wrong file, most tasks missing, invented results, empty)
go below 5. Final grade rounds **up** to the next 0.5. Proven AI use costs 1 point; every
other suspicion is a note for you, never an automatic deduction.

## Why it's cheap

| Step | Done by | Cost |
|---|---|---|
| Text, screenshots, OCR, metadata | local Python + tesseract | free |
| Copy check, AI-signal scan, curve, CSVs | local Python | free |
| Grading (batches of 6, in parallel) | Haiku (Claude) / Luna (Codex) | low |
| Review of flagged cases only | Sonnet (Claude) / Terra (Codex) | medium |

The main session never reads submissions itself. A 41-student class took ~8 cheap agent runs
plus ~5 review runs.

## Requirements

- Claude Code **or** OpenAI Codex CLI
- Python 3.9+ with `PyMuPDF` and `Pillow`
- `tesseract` OCR (optional, strongly recommended: it reads terminal screenshots for free)

## Installation

```bash
git clone https://github.com/yasserhegazy/lab-grader-skill.git
cd lab-grader-skill
./install.sh                     # installs for every agent it finds
```

Then install the Python packages and OCR if the installer reports them missing:

```bash
python3 -m pip install --user -r requirements.txt      # Ubuntu 23.04+: add --break-system-packages, or use a venv
sudo apt install -y tesseract-ocr                       # macOS: brew install tesseract
```

Restart Claude Code / Codex afterwards so the skill is picked up.

### Claude Code only

```bash
./install.sh --claude            # -> ~/.claude/skills/lab-grader
```

or manually: `cp -r skills/lab-grader ~/.claude/skills/`

Agents: graders run on **Haiku**, reviewers on **Sonnet** (set automatically through the
Agent tool).

### Codex only

```bash
./install.sh --codex             # -> ~/.codex/skills/lab-grader  (respects $CODEX_HOME)
```

or manually: `cp -r skills/lab-grader ~/.codex/skills/`

Agents: graders run on the newest **Luna** (`gpt-6-luna`), reviewers on the newest **Terra**
(`gpt-5.6-terra`), each as a sandboxed parallel `codex exec` process. When newer models ship, pass
them with `--model` (the skill tells Codex how), or change the defaults at the top of
`skills/lab-grader/scripts/codex_agents.py`.

### Updating

```bash
cd lab-grader-skill && git pull && ./install.sh
```

The previous install is backed up next to the new one. Use `./install.sh --link` to symlink
instead of copying, so `git pull` alone updates the skill.

## Usage

Open Claude Code or Codex in the folder that contains the assignment file and the submissions
folder, and say something like:

> grade the submissions in this folder

The skill walks you through it:

1. **Extract** all submissions locally (PDF/DOCX/images/code/zip) and run the copy check
2. **Rubric**: proposed from the assignment; you approve or adjust it
3. **Pilot**: 5 random students graded; you check the grades and feedback
4. **Full run**: parallel grading of everyone
5. **Review**: flagged and spot-check cases re-checked by the stronger model
6. **AI & integrity review**: notes with evidence, "too bad" decisions, proven-AI penalty
7. **Merge**: curve, bonus, CSVs and the flags report in `<assignment folder>/grading/`

Changing one student afterwards: *"give student 1234567 a 7"*. The skill records it as a TA
override and re-merges.

## Output files (`grading/`)

| File | What it is |
|---|---|
| `grades.csv` | one row per student: every rubric item, raw → curved → bonus → AI penalty → final /10, AI level + note + question to ask, copy pairs, feedback (opens correctly in Excel) |
| `moodle_import.csv` | upload via *Assignment → Grading action → Upload grading worksheet* (pass Moodle's own worksheet with `--moodle-worksheet` for an exact match) |
| `flags.md` | grade distribution and every student that needs a human look |
| `rubric.json` / `rubric.md` | the approved rubric (reused on re-runs) |
| `similarity.md`, `ai_scan.json` | raw copy-check and AI-signal results |

## Privacy

Everything except the agent calls runs locally. Submissions are read by the agent you already
use (Claude or Codex) and nothing is uploaded anywhere else. Never commit the `grading/`
folder or student files; `.gitignore` already excludes them.

## Customising

- **Feedback language/tone**: `skills/lab-grader/references/worker-prompt.md`, step 7
- **Grading policy** (weights, curve, bonus, AI penalty): `references/rubric-guide.md`, and per
  assignment in `grading/rubric.json` (`curve`, `ai_penalty_high_proven`, `lab_allowlist`)
- **AI signals**: `references/ai-signals.md` (guide for the reviewers) and `scripts/ai_scan.py`
  (free scanner)

## Layout

```
skills/lab-grader/
├── SKILL.md                    workflow the agent follows
├── references/                 briefs for graders / reviewers, rubric + AI guides
└── scripts/
    ├── extract.py              text, screenshots, OCR, metadata (parallel, free)
    ├── similarity.py           copy & paraphrase detection between students
    ├── ai_scan.py              free AI / fabrication / beyond-the-lab scan
    ├── plan.py                 balanced batches, review and AI case lists
    ├── codex_agents.py         parallel `codex exec` launcher (Codex harness)
    └── merge.py                curve, bonus, penalties → CSVs + flags report
```

## License

MIT
