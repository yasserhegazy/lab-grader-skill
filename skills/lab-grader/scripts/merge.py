#!/usr/bin/env python3
"""Merge per-student grade JSON files into the final CSVs.

Usage:
    python3 merge.py <work_dir> [--moodle-worksheet grading_worksheet.csv] [--moodle-scale 10|100]

Reads  <work_dir>/rubric.json, <work_dir>/grades/<pid>.json, manifest.json, similarity.json
Writes <work_dir>/grades.csv          (UTF-8 with BOM so Excel shows Arabic correctly)
                                      participant id, university id, name, grade, "Check", "What to do",
                                      feedback, item points, then the score steps; flagged students first
       <work_dir>/moodle_import.csv   (fills the Moodle worksheet if given, else a minimal one)

"Check" / "What to do" come from grades/<pid>.json "ta_check" {"check", "what_to_do"} (written
by the Sonnet reviewers in plain English); when missing they are derived from the other fields.

Scoring (the script computes this; agents never do the final arithmetic):
    raw_100    = sum(items.awarded) + format.awarded - global deductions          (pure rubric)
    curved_100 = rubric "curve" (default stretch): the Nth-lowest genuine attempt (curve.anchor_rank, default 5) -> 60
                 (anyone below it also gets 60),
                 a full 100 stays 100, linear in between. Students marked too_bad keep raw_100
                 (they are the only ones who can end below 5) and don't set the anchor.
    total_100  = curved_100 + bonus - ai_penalty (AI level "high" AND proven) + ta_adjustment.points
                 clamped to [0, rubric.max_total], then minus the late penalty:
                 rubric "deadline" (local time, e.g. "2026-10-24T00:00") vs manifest submitted_at
                 (upload time kept in the Moodle zip); rubric "late_penalty" default
                 [{"max_hours": 24, "points": 10}, {"max_hours": null, "points": 20}] = -1 / -2 grades
    grade_10   = total_100 / 10 rounded UP to the next 0.5   (87 -> 9.0, 81 -> 8.5, 80 -> 8.0)
                 ta_adjustment.target_grade_10, if set, replaces it (TA's final word).
"""
import argparse
import csv
import json
import math
import os
import re
from datetime import datetime

# University student number. Default fits IUG-style 9-digit ids (120230289); set
# rubric "student_id_regex" for other formats. Looked up in file names, then the report
# text, then the OCR; a number written after "ID" / "رقم" is accepted as a fallback.
DEFAULT_ID_RE = r"(?<!\d)(1\d{8})(?!\d)"
LABEL_ID_RE = re.compile(r"(?:\bID|\bNo\.?|رقم[^\d\n]{0,15})\s*[:#]?\s*(\d{7,10})\b", re.I)


def find_student_id(W, pid, files, id_re):
    base = os.path.join(W, "extracted", pid)
    def read(name, n):
        try:
            return open(os.path.join(base, name), encoding="utf-8", errors="replace").read()[:n]
        except OSError:
            return ""
    sources = [" ".join(files), read("text.txt", 6000), read("ocr.txt", 6000)]
    for src in sources:
        m = id_re.search(src)
        if m:
            return m.group(1)
    for src in sources[1:]:
        m = LABEL_ID_RE.search(src)
        if m:
            return m.group(1)
    return ""


def ceil_half(x):
    return math.ceil(round(x * 2, 6)) / 2



def short(text, n=220):
    text = " ".join(str(text).split())
    if len(text) <= n:
        return text
    cut = text[:n]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[:end + 1] if end > 60 else cut.rstrip() + "...")


def derive_check(g, row, copy_pairs_real):
    """Fallback plain-language label + action when no reviewer wrote ta_check."""
    labels, todo = [], []
    if row["too_bad"]:
        labels.append("Too bad"); todo.append(short(row["too_bad"], 140))
    if row["ai_penalty"]:
        labels.append("AI proven (-1)")
    elif row["ai_level"] in ("medium", "high"):
        labels.append("Maybe AI")
    for c in copy_pairs_real:
        labels.append(f"Copy with {c.split('(')[0]}")
    if (g.get("needs_review") or row["confidence"] == "low") and not labels:
        labels.append("Check grade"); todo.append(short(g.get("ta_notes", ""), 160))
    if row["ai_ask_student"] and labels and labels != ["Check grade"]:
        todo.append("Ask: " + short(row["ai_ask_student"], 160))
    return (" + ".join(labels) or "OK"), " ".join(t for t in todo if t)


def late_penalty(rubric, submitted_at):
    """(hours_late, points) for a submission; (0, 0) when on time or no deadline is set."""
    dl = rubric.get("deadline")
    if not dl or not submitted_at:
        return 0.0, 0.0
    hours = (datetime.fromisoformat(submitted_at) - datetime.fromisoformat(dl)).total_seconds() / 3600
    if hours <= 0:
        return 0.0, 0.0
    for step in rubric.get("late_penalty", [{"max_hours": 24, "points": 10}, {"max_hours": None, "points": 20}]):
        if step.get("max_hours") is None or hours <= step["max_hours"]:
            return hours, float(step["points"])
    return hours, 0.0


def late_text(hours):
    return f"{hours:.0f} hours" if hours < 48 else f"{hours / 24:.1f} days"


def severity(check):
    c = check.lower()
    order = [("too bad", 0), ("wrong file", 0), ("proven", 1), ("copy", 2), ("ai", 3), ("check", 4)]
    for key, sev in order:
        if key in c:
            return sev
    return 9 if c in ("ok", "") else 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--moodle-worksheet")
    ap.add_argument("--moodle-scale", type=int, default=10)
    a = ap.parse_args()
    W = a.work_dir

    rubric = json.load(open(os.path.join(W, "rubric.json")))
    man = {r["participant_id"]: r for r in json.load(open(os.path.join(W, "manifest.json")))}
    sim_path = os.path.join(W, "similarity.json")
    sim = json.load(open(sim_path)) if os.path.exists(sim_path) else []
    copy_of = {}
    for p in sim:
        if p["level"] in ("medium", "high"):
            copy_of.setdefault(p["a"], []).append(f"{p['b']}({p['level']})")
            copy_of.setdefault(p["b"], []).append(f"{p['a']}({p['level']})")

    item_ids = [it["id"] for it in rubric["items"]]
    max_total = rubric.get("max_total", 110)
    # Moodle's maximum grade is the TA's answer, never assumed: grades are capped to it.
    moodle_max = rubric.get("moodle_max_grade")
    if moodle_max is None:
        print("WARNING: rubric has no moodle_max_grade. Ask the TA what maximum grade Moodle allows "
              "for this assignment (e.g. 10 or 11) and add it to rubric.json.")
    else:
        max_total = min(max_total, 10 * float(moodle_max))
    maxes = {it["id"]: it["max"] for it in rubric["items"]}
    gids = {d["id"] for d in rubric.get("global_deductions", [])}
    curve = rubric.get("curve", {"method": "stretch", "min_grade_10": 6, "max_grade_10": 10})
    ai_pen_pts = float(rubric.get("ai_penalty_high_proven", 10))
    ai_scan_path = os.path.join(W, "ai_scan.json")
    ai_scan = json.load(open(ai_scan_path)) if os.path.exists(ai_scan_path) else {}
    id_re = re.compile(rubric.get("student_id_regex", DEFAULT_ID_RE))
    rows, problems, G = [], [], {}

    # pass 1: pure rubric score per student
    for pid in sorted(man):
        gp = os.path.join(W, "grades", f"{pid}.json")
        if not os.path.exists(gp):
            problems.append(f"- {pid} {man[pid]['name']}: **NOT GRADED YET**")
            continue
        g = json.load(open(gp))
        awarded = {it["id"]: float(it["awarded"]) for it in g.get("items", [])}
        for k, v in awarded.items():
            if k in maxes and v > maxes[k]:
                problems.append(f"- {pid}: item {k} awarded {v} > max {maxes[k]}, clipped")
                awarded[k] = maxes[k]
        fmt = min(float(g.get("format", {}).get("awarded", 0)), rubric["format"]["max"])
        # Only submission-level (global) deductions belong here; item deductions are already
        # inside items[].awarded. Workers sometimes list them twice, so ignore the extras.
        stray = [d for d in g.get("deductions", []) if d.get("id") not in gids]
        if stray:
            problems.append(f"- {pid}: ignored non-global deductions (already inside item scores): {[d.get('id') for d in stray]}")
        ded = sum(float(d["points"]) for d in g.get("deductions", []) if d.get("id") in gids)
        G[pid] = (g, awarded, fmt, ded, max(0.0, sum(awarded.values()) + fmt - ded))

    # curve anchor: weakest real attempt
    # Anchor on the Nth-lowest genuine attempt (default 5th) so a single very weak student
    # doesn't lift the whole class; anyone below the anchor gets the floor (6.0).
    real = sorted(v[4] for v in G.values() if not v[0].get("too_bad", {}).get("is"))
    rank = int(curve.get("anchor_rank", 5))
    lo = real[min(rank, len(real)) - 1] if real else 0.0
    c_lo, c_hi = 10 * curve.get("min_grade_10", 6), 10 * curve.get("max_grade_10", 10)

    # pass 2: curve, bonus, AI penalty, TA override
    for pid, (g, awarded, fmt, ded, raw) in G.items():
        too_bad = bool(g.get("too_bad", {}).get("is"))
        if too_bad or curve.get("method") == "none":
            curved = raw
        elif lo >= 100:
            curved = c_hi
        else:
            curved = c_lo + (c_hi - c_lo) * max(0.0, raw - lo) / (100 - lo)
        bonus = min(float(g.get("bonus", {}).get("awarded", 0)), rubric["bonus"]["max"])
        ai = g.get("ai", {})
        ai_pen = ai_pen_pts if ai.get("level") == "high" and ai.get("proven") else 0.0
        adj = g.get("ta_adjustment", {})
        total = max(0.0, min(max_total, curved + bonus - ai_pen + float(adj.get("points", 0))))
        late_h, late_pen = late_penalty(rubric, man[pid].get("submitted_at", ""))
        total = max(0.0, total - late_pen)
        grade = float(adj["target_grade_10"]) if "target_grade_10" in adj else ceil_half(total / 10)
        sid = find_student_id(W, pid, man[pid].get("files", []), id_re)
        row = {
            "participant_id": pid, "student_id": sid, "name": man[pid]["name"], "grade_10": grade,
            "Check": "", "What to do": "", "feedback_ar": g.get("feedback_ar", ""),
            **{k: awarded.get(k, 0) for k in item_ids},
            "format": fmt, "bonus": bonus, "deductions": ded, "ai_penalty": ai_pen, "late_penalty": late_pen,
            "raw_100": round(raw, 2), "curved_100": round(curved, 2), "total_100": round(total, 2),
        }
        # fields used only to build Check / What to do (not written to the CSV)
        info = {"too_bad": g.get("too_bad", {}).get("reason", "") if too_bad else "",
                "ai_level": ai.get("level", "none"), "ai_ask_student": ai.get("ask_student", ""),
                "confidence": g.get("confidence", "")}
        tc = g.get("ta_check") or {}
        if tc.get("check"):
            row["Check"], row["What to do"] = tc["check"], tc.get("what_to_do", "")
        else:
            row["Check"], row["What to do"] = derive_check(g, {**row, **info}, copy_of.get(pid, []))
        if late_pen:
            row["Check"] = (f"Late (-{late_pen / 10:g})" if row["Check"] == "OK"
                            else f"{row['Check']} + Late (-{late_pen / 10:g})")
            row["What to do"] = (f"Submitted {late_text(late_h)} late ({man[pid]['submitted_at'].replace('T', ' ')}), "
                                 f"-{late_pen / 10:g} applied. " + row["What to do"]).strip()
            row["feedback_ar"] = (row["feedback_ar"].rstrip() +
                                  f" (ملاحظة: انخصم {'علامة' if late_pen <= 10 else 'علامتين'} بسبب التسليم المتأخر)")
        if adj:
            row["What to do"] = (row["What to do"] + f" Grade adjusted by TA: {adj.get('reason', '')}").strip()
        if not sid:
            row["What to do"] = (row["What to do"] + " No university ID found in the report.").strip()
        rows.append(row)
    rows.sort(key=lambda r: (severity(r["Check"]), r["participant_id"]))

    if rows:
        with open(os.path.join(W, "grades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

    # Moodle: the offline grading worksheet identifies students as "Participant <id>",
    # the same number Moodle puts in the downloaded folder names.
    by_pid = {r["participant_id"]: r for r in rows}
    scale = lambda r: r["grade_10"] if a.moodle_scale == 10 else round(r["total_100"], 2)
    over_max = [r for r in rows if r["grade_10"] > (float(moodle_max) if moodle_max is not None else 10)]
    out = os.path.join(W, "moodle_import.csv")
    if a.moodle_worksheet:
        with open(a.moodle_worksheet, encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh); fields = rd.fieldnames; ws = list(rd)
        for r in ws:
            pid = r.get("Identifier", "").replace("Participant", "").strip()
            if pid in by_pid:
                r["Grade"] = scale(by_pid[pid])
                if "Feedback comments" in r:
                    r["Feedback comments"] = by_pid[pid]["feedback_ar"]
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(ws)
    else:
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Identifier", "Full name", "Grade", "Feedback comments"])
            for r in rows:
                w.writerow([f"Participant {r['participant_id']}", r["name"], scale(r), r["feedback_ar"]])

    dist = {}
    for r in rows:
        dist[r["grade_10"]] = dist.get(r["grade_10"], 0) + 1
    flagged = [r for r in rows if severity(r["Check"]) < 9]
    print(f"grades.csv: {len(rows)}/{len(man)} students, {len(flagged)} to check (at the top) | moodle_import.csv")
    if G:
        print(f"Curve: {curve.get('method')} | anchor = genuine attempt #{rank} from the bottom, rubric {lo:.1f} -> {c_lo/10:.1f}/10, 100 -> {c_hi/10:.1f}/10")
    print("Distribution (/10): " + ", ".join(f"{k}: {v}" for k, v in sorted(dist.items())))
    if over_max:
        print(f"{len(over_max)} students above the Moodle maximum ({moodle_max or 10}): check moodle_max_grade with the TA.")
    for p_ in problems:
        print(p_)
    for r in rows:
        print(f"{r['participant_id']}  {r['grade_10']:4}  {r['Check'][:40]:<40}  {r['name'][:28]}")


if __name__ == "__main__":
    main()
