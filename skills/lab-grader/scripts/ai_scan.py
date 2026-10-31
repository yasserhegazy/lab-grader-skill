#!/usr/bin/env python3
"""Free AI-writing / fabrication scan of every submission. Zero Claude tokens.

Usage:
    python3 ai_scan.py <work_dir> --template <assignment.pdf> [<lab handout.pdf> ...]

Looks for the evidence that actually separated AI-written reports from real ones in
practice: leftover placeholders and chat phrases, raw Markdown, script-generated files,
and, strongest of all, numbers in the report text that the student's own screenshots
(OCR) contradict. Text copied from the assignment itself is removed first, so a student
quoting "replace them with your actual lab values" is not flagged.

Writes <work_dir>/ai_scan.json  {pid: {"score": n, "signals": [{"kind", "weight", "evidence"}]}}
Every student with score >= 2 goes to the Sonnet AI reviewer.
"""
import argparse
import json
import os
import re

import fitz

PLACEHOLDER = re.compile(r"\[\s*(insert|your|add|replace|paste|todo|fill|screenshot|name|id)\b[^\]]{0,200}\]|"
                         r"\breplace (this|with your)\b|<\s*your[^>\n]{0,30}>|\bTODO\b|to be filled|"
                         r"\b(?:x{1,3}\.){3}x{1,3}\b|\bXX:XX\b", re.I)
CHAT = re.compile(r"\b(certainly!|as an ai\b|i hope this helps|let me know if|feel free to|here is (your|the) "
                  r"(report|updated|revised|final)|from the user'?s|the user'?s (screenshot|output|machine)|"
                  r"based on your (screenshot|output)|you (can|should) replace|i (have|'ve) (written|prepared|created))", re.I)
MD = re.compile(r"\*\*[^*\n]{2,60}\*\*|^\s*#{2,4} \S|```|`[^`\n]{2,40}`", re.M)
AI_WORDS = re.compile(r"\b(delve|delves|crucial|robust|comprehensive|seamless(ly)?|furthermore|moreover|pivotal|"
                      r"notably|underscores?|meticulous(ly)?|intricate|leverag(e|es|ing)|realm|tapestry|"
                      r"it is worth noting|in summary|in conclusion,|plays a (key|vital|pivotal) role)\b", re.I)
EMOJI = re.compile("[✅❌✔✖\U0001F4CC\U0001F50D\U0001F680\U0001F4A1\U0001F512\U0001F310⚠]")
SCANTIME = re.compile(r"(\d+\.\d{2})\s*sec(?:ond)?s?\b", re.I)   # 2 decimals: scan times, not "3.0 seconds" timeouts
IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# "Beyond the lab": code and tool options the course never taught. Students write what the
# lab showed them; AI assistants add their own idioms. A signal for the reviewer, not proof.
CALL = re.compile(r"\b[A-Za-z_]\w*\.([A-Za-z_]\w*)\s*\(")
IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
NMAP_FLAG = re.compile(r"\bnmap\b[^\n]*?((?:\s--?[A-Za-z][\w-]*)+)")
IDIOMS = {
    "if __name__ == '__main__'": re.compile(r"if\s+__name__\s*=="),
    "argparse / sys.argv": re.compile(r"\b(argparse|sys\.argv)\b"),
    "threads / async": re.compile(r"\b(threading|concurrent\.futures|asyncio|multiprocessing)\b"),
    "type hints": re.compile(r"def \w+\([^)]*\w+\s*:\s*(int|str|list|dict|float|tuple)\b|\)\s*->\s*\w+"),
    "docstrings": re.compile(r'^\s*(\"\"\"|\'\'\')', re.M),
    "classes / dataclasses": re.compile(r"^\s*(class\s+\w+|@dataclass)", re.M),
    "logging / colored output": re.compile(r"\b(logging\.|colorama|termcolor)|\\033\["),
    "errno tables": re.compile(r"\berrno\.errorcode\b"),
}
DEFAULT_IP = re.compile(r"^(127\.|0\.0\.0\.0|255\.|8\.8\.|10\.0\.2\.(2|3|4|15|255)$)")


def norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--template", nargs="*", default=[])
    a = ap.parse_args()
    W = a.work_dir
    tmpl = "\n".join("".join(p.get_text() for p in fitz.open(t)) for t in a.template)
    # Only remove copied assignment *prose* (6+ words); a pasted command line such as
    # "nmap -sT -p 22,80,443 192.168.56.20" must stay, since that is itself a signal.
    tmpl_lines = {norm(l) for l in tmpl.splitlines() if len(l.split()) >= 6}
    tmpl_ips = set(IP.findall(tmpl))
    lab_calls = set(CALL.findall(tmpl))
    lab_imports = {(a or b).split(".")[0] for a, b in IMPORT.findall(tmpl)}
    lab_flags = {f for m in NMAP_FLAG.findall(tmpl) for f in m.split()}
    lab_idioms = {k for k, rx in IDIOMS.items() if rx.search(tmpl)}
    # Agents compare explanations against the course material, so keep a cheap text copy.
    with open(os.path.join(W, "lab_reference.txt"), "w") as fh:
        fh.write(tmpl)

    # Things the assignment requires without naming the function (e.g. "set a 3-second timeout"
    # -> settimeout). The main session fills rubric.json "lab_allowlist" when building the rubric.
    rub_path = os.path.join(W, "rubric.json")
    allow = set(json.load(open(rub_path)).get("lab_allowlist", [])) if os.path.exists(rub_path) else set()
    NOT_CODE = {"png", "jpg", "jpeg", "txt", "py", "pdf", "docx", "com", "org", "net", "local", "html", "sh"}

    man = json.load(open(os.path.join(W, "manifest.json")))
    # pass 1: what each student uses beyond the lab, so class-wide habits weigh less
    beyond_of = {}
    for r in man:
        d = os.path.join(W, "extracted", r["participant_id"])
        both = open(os.path.join(d, "text.txt"), errors="replace").read() + "\n" + open(os.path.join(d, "ocr.txt"), errors="replace").read()
        calls = set(CALL.findall(both)) - lab_calls - allow - NOT_CODE
        imps = {(x or y).split(".")[0] for x, y in IMPORT.findall(both)} - lab_imports - allow
        idi = {k for k, rx in IDIOMS.items() if k not in lab_idioms and rx.search(both)}
        flags = {f for m in NMAP_FLAG.findall(both) for f in m.split()} - lab_flags - allow
        beyond_of[r["participant_id"]] = (sorted(imps), sorted(calls), sorted(idi), sorted(flags))
    share = {}
    for v in beyond_of.values():
        for x in set(v[0]) | set(v[1]) | set(v[2]):
            share[x] = share.get(x, 0) + 1
    out = {}
    for r in man:
        pid = r["participant_id"]
        d = os.path.join(W, "extracted", pid)
        raw = open(os.path.join(d, "text.txt"), errors="replace").read()
        ocr = open(os.path.join(d, "ocr.txt"), errors="replace").read()
        text = "\n".join(l for l in raw.splitlines() if norm(l) not in tmpl_lines)
        words = max(1, len(text.split()))
        sig = []

        def add(kind, w, ev):
            sig.append({"kind": kind, "weight": w, "evidence": ev})

        for f in r["flags"]:
            if f.startswith("META_SCRIPT_GENERATED"):
                add("script-generated file", 3, f.split(" (")[0])
            elif f.startswith("META_DOCX_EDIT_TIME"):
                add("document edited for almost no time", 2, f.split(" (")[0])
            elif f.startswith("META_BROWSER_PRINT"):
                add("printed from a browser (weak)", 0.5, f.split(" (")[0])
        ph = sorted({m.group(0) for m in PLACEHOLDER.finditer(text)})
        if ph:
            add("leftover placeholders", 3, [re.sub(r"\s+", " ", x)[:80] for x in ph[:5]])
        ch = sorted({m.group(0) for m in CHAT.finditer(text)})
        if ch:
            add("chat-assistant leftovers", 3, ch[:5])
        md = [m.group(0).strip() for m in MD.finditer(text)]
        if len(md) >= 2:
            add("raw Markdown in PDF", 1.5, md[:4])
        aw = [m.group(0).lower() for m in AI_WORDS.finditer(text)]
        if len(aw) * 1000 / words >= 4 and len(aw) >= 4:
            add("AI-typical vocabulary density", 1, f"{len(aw)} hits/{words} words: {sorted(set(aw))[:8]}")
        dashes = text.count("—")
        if dashes * 1000 / words >= 3 and dashes >= 4:
            add("heavy em-dash use", 0.5, f"{dashes} em-dashes")
        if EMOJI.search(text):
            add("emoji / check-mark bullets", 1, sorted(set(EMOJI.findall(text)))[:6])
        out_imps, out_calls, out_idioms, out_flags = beyond_of[pid]
        beyond = out_imps + out_calls + out_idioms
        if beyond:
            # rare constructs count fully; ones a third of the class used count half
            n = sum(1 if share[x] <= len(man) / 3 else 0.5 for x in beyond)
            w = 0.5 if n <= 2 else (1.5 if n <= 4 else 2.5)
            add("code beyond what the lab taught", w,
                {"imports": out_imps, "calls": out_calls[:10], "idioms": out_idioms,
                 "class_share": {x: f"{share[x]}/{len(man)}" for x in beyond[:12]}})
        if out_flags:
            add("nmap options not in lab/assignment (may be typos/OCR)", min(1.0, 0.25 * len(out_flags)), out_flags[:8])
        # Fabrication: values in the text that the student's own screenshots contradict.
        t_times, o_times = set(SCANTIME.findall(text)), set(SCANTIME.findall(ocr))
        if t_times and o_times and not (t_times & o_times):
            add("scan time in text not in any screenshot", 3, f"text {sorted(t_times)} vs screenshots {sorted(o_times)}")
        o_ips = {ip for ip in IP.findall(ocr)}
        t_ips = {ip for ip in IP.findall(text) if not DEFAULT_IP.match(ip)}
        missing = sorted(ip for ip in t_ips - o_ips if not ip.endswith((".0", ".255")))
        if o_ips and missing:
            ex = [ip for ip in missing if ip in tmpl_ips]
            if ex:
                add("assignment example IPs in text, not in screenshots", 2.5, ex[:4])
            if len(missing) - len(ex) >= 2:
                add("IPs in text not seen in screenshots (check: OCR may misread)", 1, [i for i in missing if i not in ex][:4])
        score = round(sum(s["weight"] for s in sig), 1)
        out[pid] = {"name": r["name"], "score": score, "signals": sig}

    json.dump(out, open(os.path.join(W, "ai_scan.json"), "w"), ensure_ascii=False, indent=1)
    for pid, v in sorted(out.items(), key=lambda kv: -kv[1]["score"]):
        if v["score"] > 0:
            print(f"{pid} {v['score']:4}  " + "; ".join(f"{s['kind']}={s['evidence']}" for s in v["signals"])[:220])
    print(f"\n{sum(v['score'] >= 2 for v in out.values())} students with score >= 2 -> Sonnet AI review")


if __name__ == "__main__":
    main()
