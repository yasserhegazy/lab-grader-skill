#!/usr/bin/env python3
"""Build one evidence page per suspected copy pair, so the TA can verify it in a minute.

Usage:
    python3 evidence.py <work_dir> [--all]

Reads similarity.json (pairs, identical screenshots, matching sentences), manifest.json
(upload times, file names) and grades/<pid>.json (reviewer copy verdicts, if any).
Writes <work_dir>/evidence/<a>_<b>.html: identical screenshots side by side, matching
sentences, upload times and the reviewers' verdict. Pages link the images from
extracted/, so open them from the grading folder (they are not standalone).

By default only pairs worth a look are built: similarity level medium/high, or a reviewer
verdict of strong/possible. --all builds every pair in similarity.json.
"""
import argparse
import html
import json
import os

CSS = """
body{font-family:system-ui,sans-serif;margin:16px;max-width:1200px;color:#111;background:#fff}
h1{font-size:20px}h2{font-size:16px;margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px;vertical-align:top;text-align:left}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0}
.pair img{width:100%;border:1px solid #ccc}
.cap{font-size:12px;color:#555}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-weight:600}
.strong{background:#fde2e2;color:#9b1c1c}.possible{background:#fff4d6;color:#8a5a00}.cleared{background:#e3f6e8;color:#1d6b35}
.warn{background:#fff4d6;border:1px solid #f0d58c;padding:8px;border-radius:6px}
"""


def verdict(g, other):
    for c in g.get("copy", []) or []:
        if str(c.get("with")) == other:
            return c
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    W = a.work_dir
    pairs = json.load(open(os.path.join(W, "similarity.json")))
    man = {r["participant_id"]: r for r in json.load(open(os.path.join(W, "manifest.json")))}

    def grade(pid):
        p = os.path.join(W, "grades", f"{pid}.json")
        return json.load(open(p)) if os.path.exists(p) else {}

    out_dir = os.path.join(W, "evidence")
    os.makedirs(out_dir, exist_ok=True)
    built = []
    for p in pairs:
        A, B = sorted([p["a"], p["b"]])
        if A != p["a"]:  # keep each side's evidence with its student
            p = {**p, "evidence": {**p.get("evidence", {}),
                 "identical_screenshots": [[y, x] for x, y in p.get("evidence", {}).get("identical_screenshots", [])],
                 "paraphrased_sentences": [s.replace("A: ", "\0").replace("B: ", "A: ").replace("\0", "B: ")
                                           if " || " in s else s for s in p.get("evidence", {}).get("paraphrased_sentences", [])]}}
        ga, gb = grade(A), grade(B)
        va, vb = verdict(ga, B), verdict(gb, A)
        levels = {va.get("level"), vb.get("level")}
        if not (a.all or p["level"] in ("medium", "high") or levels & {"strong", "possible"}):
            continue
        ev = p.get("evidence", {})
        lvl = va.get("level") or vb.get("level") or "not reviewed"
        h = [f"<!doctype html><meta charset='utf-8'><title>Evidence {A} vs {B}</title><style>{CSS}</style>",
             f"<h1>Possible copy: {A} vs {B}</h1>",
             f"<p>Reviewer verdict: <span class='badge {html.escape(lvl)}'>{html.escape(lvl)}</span> "
             f"&nbsp; automatic similarity: <b>{html.escape(p['level'])}</b> (score {p.get('score', '')})</p>",
             "<p class='warn'>This page shows what matches. It is not a decision: check the screenshots "
             "yourself. The suggested check values, the assignment wording and the same IDE look are "
             "allowed to match. No grade changes unless you decide.</p>",
             "<table><tr><th></th><th>" + A + "</th><th>" + B + "</th></tr>"]
        for label, fa, fb in [
            ("Name", man.get(A, {}).get("name", ""), man.get(B, {}).get("name", "")),
            ("Uploaded", man.get(A, {}).get("submitted_at", ""), man.get(B, {}).get("submitted_at", "")),
            ("Files", ", ".join(man.get(A, {}).get("files", [])), ", ".join(man.get(B, {}).get("files", []))),
            ("Signs (reviewer)", "; ".join(va.get("signs", [])), "; ".join(vb.get("signs", []))),
            ("Second opinion", json.dumps(ga.get("second_opinion", {}).get("copy", ""), ensure_ascii=False),
             json.dumps(gb.get("second_opinion", {}).get("copy", ""), ensure_ascii=False)),
        ]:
            h.append(f"<tr><th>{label}</th><td>{html.escape(str(fa))}</td><td>{html.escape(str(fb))}</td></tr>")
        h.append("</table>")
        shots = ev.get("identical_screenshots", [])
        if shots:
            h.append(f"<h2>Identical screenshots ({len(shots)})</h2>")
            for ia, ib in shots:
                h.append("<div class='pair'>"
                         f"<div><img src='../extracted/{A}/images/{ia}' loading='lazy'><div class='cap'>{A} {ia}</div></div>"
                         f"<div><img src='../extracted/{B}/images/{ib}' loading='lazy'><div class='cap'>{B} {ib}</div></div></div>")
        sents = ev.get("paraphrased_sentences", [])
        if sents:
            h.append(f"<h2>Matching sentences: {html.escape(str(sents[0]))}</h2><table><tr><th>{A}</th><th>{B}</th></tr>")
            for s in sents[1:]:
                left, _, right = s.partition(" || ")
                h.append(f"<tr><td>{html.escape(left[3:] if left.startswith('A: ') else left)}</td>"
                         f"<td>{html.escape(right[3:] if right.startswith('B: ') else right)}</td></tr>")
            h.append("</table>")
        other = {k: v for k, v in ev.items() if k not in ("identical_screenshots", "paraphrased_sentences")}
        if other:
            h.append("<h2>Other matches</h2><table>")
            for k, v in other.items():
                h.append(f"<tr><th>{html.escape(k)}</th><td>{html.escape(json.dumps(v, ensure_ascii=False))}</td></tr>")
            h.append("</table>")
        path = os.path.join(out_dir, f"{A}_{B}.html")
        open(path, "w", encoding="utf-8").write("\n".join(h))
        built.append(f"{A}_{B}.html ({lvl})")
    print(f"{len(built)} evidence pages -> {out_dir}\n" + "\n".join(built))


if __name__ == "__main__":
    main()
