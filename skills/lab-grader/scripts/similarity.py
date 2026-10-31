#!/usr/bin/env python3
"""Cross-student copy detection. Zero Claude tokens.

Usage:
    python3 similarity.py <work_dir> [--template file.pdf ...]

Pass the assignment PDF and any lab handout as --template so the text/code the
instructor gave everyone is not counted as copying.

Checks every pair of students for:
  * report text overlap (word 6-gram Jaccard, template + common boilerplate removed)
  * code overlap (code-looking lines, template + very common lines removed)
  * identical comment lines in code (strong signal)
  * identical / near-identical screenshots (perceptual hash)
  * shared RARE network evidence: IPs, MACs, nmap timestamps, latency values that
    appear in very few submissions. Defaults every VM shares (VirtualBox NAT
    10.0.2.15, gateway 10.0.2.2, loopback ...) are ignored.

Writes <work_dir>/similarity.json and <work_dir>/similarity.md.
"""
import argparse
import itertools
import json
import os
import re
from collections import Counter, defaultdict

import fitz
from PIL import Image, ImageChops, ImageStat

# Values that are identical on thousands of machines, so sharing them proves nothing.
DEFAULT_IP_RE = re.compile(
    r"^(127\.|0\.0\.0\.0|255\.|10\.0\.2\.(0|1|2|3|4|15|255)$|192\.168\.56\.(0|1|2|100|101|255)$|"
    r"192\.168\.(0|1)\.(0|1|255)$|8\.8\.|1\.1\.1\.1|224\.|169\.254\.|172\.17\.0\.(1|2)$|10\.0\.0\.(0|1)$)")
DEFAULT_MAC_PREFIX = ("52:54:00:12:35:", "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
MAC_RE = re.compile(r"\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b", re.I)
TS_RE = re.compile(r"(?:Nmap|nmap)[^\n]{0,40}? at (\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
LAT_RE = re.compile(r"\((\d\.\d{4,})s latency\)")
SCANTIME_RE = re.compile(r"scanned in (\d+\.\d{2}) seconds")
# Shell prompt "user@host:" in a screenshot names whose machine produced it.
PROMPT_RE = re.compile(r"\b([a-z_][a-z0-9_.-]{1,30}@[A-Za-z0-9_-]{2,40})(?=\s?:\s?[~/])")
DEFAULT_PROMPTS = {"ubuntu@ubuntu", "kali@kali", "root@kali", "root@ubuntu", "user@ubuntu", "user@user",
                   "vboxuser@ubuntu", "ubuntu@ubuntu-virtualbox", "student@ubuntu"}
CODE_HINT = re.compile(r"(^\s*(import|from|def|class|for|while|if|elif|else|try|except|finally|return|with|print)\b)|"
                       r"(\w+\s*=\s*\S)|(\w+\.\w+\()|(^\s*#)|(^\s*(#include|int |void |std::|cout|printf))")


def norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def read(p):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except FileNotFoundError:
        return ""


def template_text(paths):
    out = []
    for p in paths:
        if p.lower().endswith(".pdf"):
            out.append("".join(pg.get_text() for pg in fitz.open(p)))
        else:
            out.append(read(p))
    return "\n".join(out)


def shingles(text, n=6):
    w = re.findall(r"[a-z0-9_]+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


# Captions that just name an instruction and a register value ("mov eax, 6 executed -> EAX =
# 00000006") are near-identical for every honest student, so they don't count as paraphrase.
CODEY = re.compile(r"\b(e?[abcd]x|[abcd][lh]|e?[sd]i|e?[sb]p|eip|0x[0-9a-f]+|[0-9a-f]{4,8}h?|\d+(\.\d+){3}|"
                   r"port \d+|connect_ex|nmap|mov|add|sub)\b", re.I)


def sentences(t):
    out = []
    for x in re.split(r"(?<=[.!?])\s+|\n", t):
        w = x.split()
        if len(w) >= 7 and len(CODEY.findall(x)) / len(w) < 0.25:
            out.append(re.sub(r"\s+", " ", x.strip().lower()))
    return out


def grams4(s):
    return {s[i:i + 4] for i in range(len(s) - 3)}


def paraphrased(A, B, th=0.45):
    """Sentences of A that have a reworded twin in B (char 4-gram Jaccard). Catches two
    reports produced from one source (same AI prompt, or one rewording the other) that
    word-sequence overlap misses: "Full Agreement" vs "100% Agreement"."""
    hits = []
    for x, gx in A:
        for y, gy in B:
            if len(gx & gy) / len(gx | gy) > th:
                hits.append((x, y)); break
    return hits


def ham(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def pixel_diff(work, x, fx, y, fy):
    """Mean grey-level difference at 256x256 (0 = identical). Confirms a hash match."""
    try:
        A = Image.open(os.path.join(work, "extracted", x, "images", fx)).convert("L").resize((256, 256))
        B = Image.open(os.path.join(work, "extracted", y, "images", fy)).convert("L").resize((256, 256))
        return ImageStat.Stat(ImageChops.difference(A, B)).mean[0]
    except Exception:
        return 255


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--template", nargs="*", default=[])
    ap.add_argument("--text-th", type=float, default=0.20)
    ap.add_argument("--code-th", type=float, default=0.55)
    a = ap.parse_args()

    man = json.load(open(os.path.join(a.work_dir, "manifest.json")))
    ids = [r["participant_id"] for r in man]
    names = {r["participant_id"]: r["name"] for r in man}
    N = len(ids)
    tmpl = template_text(a.template)
    tmpl_lines = {norm(l) for l in tmpl.splitlines() if norm(l)}
    tmpl_sh = shingles(tmpl)

    text, code, comments, net, hashes, sents = {}, {}, {}, {}, {}, {}
    tmpl_sents = [grams4(x) for x in sentences(tmpl)]
    for pid in ids:
        d = os.path.join(a.work_dir, "extracted", pid)
        body = read(os.path.join(d, "text.txt"))
        ocr = read(os.path.join(d, "ocr.txt"))
        both = body + "\n" + ocr
        text[pid] = body
        # Drop sentences that paraphrase the assignment itself; everybody does that.
        sents[pid] = [(x, g) for x, g in ((x, grams4(x)) for x in sentences(body))
                      if not any(len(g & t) / len(g | t) > 0.5 for t in tmpl_sents)]
        lines = [norm(l) for l in both.splitlines()]
        code[pid] = {l for l in lines if len(l) > 8 and CODE_HINT.search(l) and l not in tmpl_lines}
        comments[pid] = {l for l in code[pid] if l.startswith("#") and len(l) > 15}
        toks = set()
        for ip in IP_RE.findall(both):
            if not DEFAULT_IP_RE.match(ip) and all(0 <= int(x) <= 255 for x in ip.split(".")):
                toks.add("ip:" + ip)
        for mac in MAC_RE.findall(both):
            m = mac.lower().replace("-", ":")
            if not m.startswith(DEFAULT_MAC_PREFIX):
                toks.add("mac:" + m)
        toks |= {"time:" + t for t in TS_RE.findall(both)}
        toks |= {"latency:" + t for t in LAT_RE.findall(both)}
        toks |= {"scantime:" + t for t in SCANTIME_RE.findall(both)}
        toks |= {"prompt:" + p.lower() for p in PROMPT_RE.findall(ocr)
                 if p.lower() not in DEFAULT_PROMPTS and not p.lower().startswith(("vboxuser@", "enp", "eth"))}
        net[pid] = {t for t in toks if t.split(":", 1)[1] not in tmpl}
        meta = json.load(open(os.path.join(d, "meta.json")))
        # Cover-page images are logos / decorative stock photos, not evidence.
        hashes[pid] = [(im["file"], im["dhash"]) for im in meta.get("images", []) if im.get("page") != 1]

    # Remove boilerplate everybody shares (headings, assignment wording they pasted, the lab code).
    line_df = Counter(l for pid in ids for l in code[pid])
    common_line = {l for l, c in line_df.items() if c > max(3, 0.3 * N)}
    sh = {pid: shingles(text[pid]) - tmpl_sh for pid in ids}
    sh_df = Counter(s for pid in ids for s in sh[pid])
    common_sh = {s for s, c in sh_df.items() if c > max(3, 0.25 * N)}
    for pid in ids:
        sh[pid] -= common_sh
        code[pid] -= common_line
        comments[pid] -= common_line
    tok_df = Counter(t for pid in ids for t in net[pid])
    # An image near-matching images of many students is a logo / header / stock picture.
    # Count students per image by near-match, since rescaling changes the hash slightly.
    hash_df = Counter()
    for pid in ids:
        for _, h in hashes[pid]:
            hash_df[h] = sum(1 for q in ids if any(ham(h, h2) <= 8 for _, h2 in hashes[q]))

    pairs = []
    for x, y in itertools.combinations(ids, 2):
        ev, score = {}, 0.0
        tj = jac(sh[x], sh[y])
        cj = jac(code[x], code[y])
        same_comments = sorted(comments[x] & comments[y])
        rare = sorted(t for t in net[x] & net[y] if tok_df[t] <= 3)
        same_imgs = [(fx, fy) for fx, hx in hashes[x] for fy, hy in hashes[y]
                     if hash_df[hx] <= 2 and hash_df[hy] <= 2 and ham(hx, hy) <= 4
                     and pixel_diff(a.work_dir, x, fx, y, fy) <= 6]
        if tj >= a.text_th:
            ev["text_overlap"] = round(tj, 2); score += tj * 2
        if cj >= a.code_th and min(len(code[x]), len(code[y])) >= 5:
            ev["code_overlap"] = round(cj, 2); score += cj
        if len(same_comments) >= 2:
            ev["identical_comments"] = same_comments[:6]; score += 0.3 * len(same_comments)
        # MACs and user@host prompts identify one machine. Timestamps/latencies/IPs can
        # coincide by chance (same lab hour, tiny scan times), so only count them together.
        strong = [t for t in rare if t.startswith(("mac:", "prompt:"))]
        if strong or len(rare) >= 3:
            ev["shared_rare_network_evidence"] = rare[:10]; score += 0.5 * len(strong) + 0.15 * len(rare)
        para = paraphrased(sents[x], sents[y])
        ratio = len(para) / max(1, min(len(sents[x]), len(sents[y])))
        if len(para) >= 6 and ratio >= 0.12:   # in a 41-student class every innocent pair had <= 5
            ev["paraphrased_sentences"] = [f"{len(para)} sentences ({ratio:.0%})"] + [f"A: {u[:90]} || B: {v[:90]}" for u, v in para[:4]]
            score += 0.08 * len(para)
        if same_imgs:
            ev["identical_screenshots"] = same_imgs[:6]; score += 1.0 * len(same_imgs)
        if ev:
            level = "high" if score >= 2 or same_imgs or len(strong) >= 2 else ("medium" if score >= 0.8 else "low")
            pairs.append({"a": x, "b": y, "a_name": names[x], "b_name": names[y],
                          "level": level, "score": round(score, 2), "evidence": ev})
    pairs.sort(key=lambda p: -p["score"])

    with open(os.path.join(a.work_dir, "similarity.json"), "w") as fh:
        json.dump(pairs, fh, ensure_ascii=False, indent=1)
    md = ["# Copy-check between students\n",
          f"{N} submissions, {len(pairs)} suspicious pairs. Template text/code removed; VirtualBox/loopback defaults ignored.\n",
          "| level | score | student A | student B | evidence |", "|---|---|---|---|---|"]
    for p in pairs:
        ev = "; ".join(f"{k}={v}" for k, v in p["evidence"].items())
        md.append(f"| {p['level']} | {p['score']} | {p['a']} {p['a_name']} | {p['b']} {p['b_name']} | {ev[:400]} |")
    with open(os.path.join(a.work_dir, "similarity.md"), "w") as fh:
        fh.write("\n".join(md) + "\n")
    print("\n".join(md[:40]))


if __name__ == "__main__":
    main()
