#!/usr/bin/env python3
"""Plan the agent work: balanced grading batches, then the Sonnet review list.

Usage:
    python3 plan.py <work_dir> batches [--size 6] [--exclude pid ...]
        -> writes <work_dir>/batches.json and prints one batch per line
    python3 plan.py <work_dir> ai
        -> students for the Sonnet AI/integrity reviewer: ai_scan score >= 2, worker AI
           medium/high, copy pairs, too-bad candidates (flag or raw rubric < 50) -> ai_cases.json
    python3 plan.py <work_dir> second
        -> serious cases for an independent second opinion (after the AI review): a copy verdict
           "strong", or AI "high" / proven -> second_cases.json. Both students of a pair are listed.
    python3 plan.py <work_dir> review
        -> reads grades/*.json + batches.json, writes <work_dir>/review_cases.json
           (AI medium/high, needs_review/low confidence, script-generated/not-PDF/
           little-text auto flags, medium/high copy pairs, and one calibration
           spot-check per batch: alternately the highest-scoring clean student,
           who is most likely over-graded, and a random clean one)
"""
import argparse
import json
import math
import os
import random


def weight(r):
    return r["text_chars"] + 800 * r["n_images"]


def batches(W, size, exclude):
    rows = [r for r in json.load(open(os.path.join(W, "manifest.json"))) if r["participant_id"] not in exclude]
    n = max(1, math.ceil(len(rows) / size))
    out, load = [[] for _ in range(n)], [0] * n
    for r in sorted(rows, key=lambda r: -weight(r)):   # heaviest first into the lightest batch
        i = load.index(min(load))
        out[i].append(r["participant_id"])
        load[i] += weight(r)
    json.dump(out, open(os.path.join(W, "batches.json"), "w"), indent=1)
    for b in out:
        print(", ".join(b))


def review(W):
    man = {r["participant_id"]: r for r in json.load(open(os.path.join(W, "manifest.json")))}
    bpath = os.path.join(W, "batches.json")
    groups = json.load(open(bpath)) if os.path.exists(bpath) else [sorted(man)]
    sim_path = os.path.join(W, "similarity.json")
    pairs = json.load(open(sim_path)) if os.path.exists(sim_path) else []
    cases = {}

    def total(g):
        return sum(i["awarded"] for i in g["items"]) + g.get("format", {}).get("awarded", 0)

    for k, grp in enumerate(groups):
        clean = []
        for pid in grp:
            gp = os.path.join(W, "grades", f"{pid}.json")
            if not os.path.exists(gp):
                cases[pid] = "NOT GRADED: grade from scratch"
                continue
            g = json.load(open(gp))
            if g.get("reviewed_by") == "sonnet":
                continue
            why = []
            ai = g.get("ai", {})
            if ai.get("level") in ("medium", "high"):
                why.append(f"AI {ai['level']}: " + "; ".join(ai.get("signals", []))[:300])
            if g.get("needs_review") or g.get("confidence") == "low":
                why.append("worker unsure: " + g.get("ta_notes", "")[:300])
            auto = [f.split(" (")[0] for f in man[pid]["flags"] if f.startswith(("META_SCRIPT", "NOT_PDF", "LITTLE_TEXT"))]
            if auto:
                why.append("auto flags: " + "; ".join(auto))
            if why:
                cases[pid] = " | ".join(why)
            else:
                clean.append((pid, total(g)))
        if clean:
            pick = max(clean, key=lambda x: x[1])[0] if k % 2 == 0 else random.Random(k).choice(clean)[0]
            cases.setdefault(pick, "calibration spot-check: verify points follow the rubric and the kindness rule")
    for p in pairs:
        if p["level"] in ("medium", "high"):
            for a, b in ((p["a"], p["b"]), (p["b"], p["a"])):
                cases[a] = (cases.get(a, "") + f" | copy pair with {b} ({p['level']}): compare side by side").strip(" |")
    json.dump(cases, open(os.path.join(W, "review_cases.json"), "w"), ensure_ascii=False, indent=1)
    print(f"{len(cases)} review cases -> review_cases.json")
    for pid, why in cases.items():
        print(f"{pid}  {why[:150]}")


def ai_cases(W):
    scan_p = os.path.join(W, "ai_scan.json")
    scan = json.load(open(scan_p)) if os.path.exists(scan_p) else {}
    sim_p = os.path.join(W, "similarity.json")
    pairs = json.load(open(sim_p)) if os.path.exists(sim_p) else []
    copy = {x for p in pairs if p["level"] in ("medium", "high") for x in (p["a"], p["b"])}
    cases = []
    for f in sorted(os.listdir(os.path.join(W, "grades"))):
        pid = f[:-5]
        g = json.load(open(os.path.join(W, "grades", f)))
        raw = sum(i["awarded"] for i in g["items"]) + g.get("format", {}).get("awarded", 0)
        if (scan.get(pid, {}).get("score", 0) >= 2 or g.get("ai", {}).get("level") in ("medium", "high")
                or pid in copy or g.get("too_bad_candidate") or raw < 50):
            cases.append(pid)
    json.dump(cases, open(os.path.join(W, "ai_cases.json"), "w"))
    print(f"{len(cases)} students -> ai_cases.json\n" + ", ".join(cases))


def second_cases(W):
    cases = []
    for f in sorted(os.listdir(os.path.join(W, "grades"))):
        pid = f[:-5]
        g = json.load(open(os.path.join(W, "grades", f)))
        ai = g.get("ai", {})
        strong = [str(c.get("with")) for c in g.get("copy", []) or [] if c.get("level") == "strong"]
        if strong or ai.get("level") == "high" or ai.get("proven"):
            for p in [pid] + strong:
                if p not in cases:
                    cases.append(p)
    json.dump(cases, open(os.path.join(W, "second_cases.json"), "w"))
    print(f"{len(cases)} students -> second_cases.json\n" + ", ".join(cases))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("mode", choices=["batches", "review", "ai", "second"])
    ap.add_argument("--size", type=int, default=6)
    ap.add_argument("--exclude", nargs="*", default=[])
    a = ap.parse_args()
    {"batches": lambda: batches(a.work_dir, a.size, set(a.exclude)),
     "review": lambda: review(a.work_dir), "ai": lambda: ai_cases(a.work_dir),
     "second": lambda: second_cases(a.work_dir)}[a.mode]()


if __name__ == "__main__":
    main()
