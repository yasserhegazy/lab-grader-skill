#!/usr/bin/env python3
"""Merge per-student grade JSON files into the final CSVs and flags report.

Usage:
    python3 merge.py <work_dir> [--moodle-worksheet grading_worksheet.csv] [--moodle-scale 10|100]

Reads  <work_dir>/rubric.json, <work_dir>/grades/<pid>.json, manifest.json, similarity.json
Writes <work_dir>/grades.csv          (UTF-8 with BOM so Excel shows Arabic correctly)
       <work_dir>/moodle_import.csv   (fills the Moodle worksheet if given, else a minimal one)
       <work_dir>/flags.md            (everything the TA must look at by hand)

Scoring (the script computes this; agents never do the final arithmetic):
    raw_100    = sum(items.awarded) + format.awarded - global deductions          (pure rubric)
    curved_100 = rubric "curve" (default stretch): the Nth-lowest genuine attempt (curve.anchor_rank, default 5) -> 60
                 (anyone below it also gets 60),
                 a full 100 stays 100, linear in between. Students marked too_bad keep raw_100
                 (they are the only ones who can end below 5) and don't set the anchor.
    total_100  = curved_100 + bonus - ai_penalty (AI level "high" AND proven) + ta_adjustment.points
                 clamped to [0, rubric.max_total]
    grade_10   = total_100 / 10 rounded UP to the next 0.5   (87 -> 9.0, 81 -> 8.5, 80 -> 8.0)
                 ta_adjustment.target_grade_10, if set, replaces it (TA's final word).
"""
import argparse
import csv
import json
import math
import os


def ceil_half(x):
    return math.ceil(round(x * 2, 6)) / 2


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
    maxes = {it["id"]: it["max"] for it in rubric["items"]}
    gids = {d["id"] for d in rubric.get("global_deductions", [])}
    curve = rubric.get("curve", {"method": "stretch", "min_grade_10": 6, "max_grade_10": 10})
    ai_pen_pts = float(rubric.get("ai_penalty_high_proven", 10))
    ai_scan_path = os.path.join(W, "ai_scan.json")
    ai_scan = json.load(open(ai_scan_path)) if os.path.exists(ai_scan_path) else {}
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
        grade = float(adj["target_grade_10"]) if "target_grade_10" in adj else ceil_half(total / 10)
        row = {
            "participant_id": pid, "name": man[pid]["name"],
            **{k: awarded.get(k, 0) for k in item_ids},
            "format": fmt, "deductions": ded, "raw_100": round(raw, 2), "too_bad": g.get("too_bad", {}).get("reason", "") if too_bad else "",
            "curved_100": round(curved, 2), "bonus": bonus, "ai_penalty": ai_pen,
            "ta_adjustment": adj.get("target_grade_10", adj.get("points", "")), "ta_adjustment_reason": adj.get("reason", ""),
            "total_100": round(total, 2), "grade_10": grade,
            "ai_level": ai.get("level", "none"), "ai_proven": bool(ai.get("proven")),
            "ai_scan_score": ai_scan.get(pid, {}).get("score", ""),
            "ai_note": ai.get("note_for_ta", " | ".join(ai.get("signals", []))),
            "ai_ask_student": ai.get("ask_student", ""),
            "copy_pairs": ", ".join(copy_of.get(pid, [])),
            "auto_flags": " | ".join(man[pid]["flags"]),
            "reviewed_by": g.get("reviewed_by", "worker"), "confidence": g.get("confidence", ""),
            "ta_notes": g.get("ta_notes", ""),
            "feedback_ar": g.get("feedback_ar", ""),
        }
        rows.append(row)
        if row["ai_level"] in ("medium", "high") or row["copy_pairs"] or too_bad or g.get("needs_review") or row["confidence"] == "low":
            problems.append(
                f"- **{pid} {row['name']}**: grade {row['grade_10']}/10 (rubric {row['raw_100']} -> curved {row['curved_100']}"
                + (f", bonus +{bonus}" if bonus else "") + (f", AI penalty -{ai_pen}" if ai_pen else "") + ")"
                + (f"\n  - **Too bad, not curved**: {row['too_bad']}" if too_bad else "")
                + (f"\n  - AI **{row['ai_level']}**{' (proven)' if row['ai_proven'] else ''}: {row['ai_note']}" if row["ai_level"] in ("medium", "high") else "")
                + (f"\n  - Ask the student: {row['ai_ask_student']}" if row["ai_ask_student"] else "")
                + (f"\n  - Similar to: {row['copy_pairs']}" if row["copy_pairs"] else "")
                + (f"\n  - Notes: {row['ta_notes']}" if row["ta_notes"] else ""))
    rows.sort(key=lambda r: r["participant_id"])
    if G:
        problems.insert(0, f"Curve: {curve.get('method')} | anchor = genuine attempt #{rank} from the bottom, rubric {lo:.1f} -> {c_lo/10:.1f}/10, 100 -> {c_hi/10:.1f}/10\n")

    if rows:
        with open(os.path.join(W, "grades.csv"), "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

    # Moodle: the offline grading worksheet identifies students as "Participant <id>",
    # the same number Moodle puts in the downloaded folder names.
    by_pid = {r["participant_id"]: r for r in rows}
    scale = lambda r: r["grade_10"] if a.moodle_scale == 10 else round(r["total_100"], 2)
    over_max = [r for r in rows if r["grade_10"] > 10]
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
    with open(os.path.join(W, "flags.md"), "w") as fh:
        fh.write(f"# Grading flags: {rubric.get('assignment', '')}\n\n")
        fh.write(f"Graded {len(rows)}/{len(man)}. Grade distribution (/10): "
                 + ", ".join(f"{k}: {v}" for k, v in sorted(dist.items())) + "\n\n")
        if over_max:
            fh.write(f"**{len(over_max)} students are above 10/10 because of the bonus.** Moodle rejects grades above the "
                     "assignment maximum unless the site setting `unlimitedgrades` is on. Raise the max or enter those by hand.\n\n")
        fh.write("## Needs TA attention\n\n" + ("\n".join(problems) if problems else "Nothing flagged.") + "\n")
    print(f"grades.csv: {len(rows)} rows | moodle_import.csv | flags.md: {len(problems)} items")
    for r in rows:
        print(f"{r['participant_id']}  {r['total_100']:6} -> {r['grade_10']:4}  ai={r['ai_level']:<6} copy={r['copy_pairs'] or '-'}  {r['name'][:28]}")


if __name__ == "__main__":
    main()
