#!/usr/bin/env python3
"""Run the grading / review agents as parallel `codex exec` processes (Codex harness).

Claude Code spawns subagents with the Agent tool; Codex has no model-selectable subagent
tool, so this launcher starts one non-interactive Codex process per batch instead.

Usage:
    python3 codex_agents.py <work_dir> worker [--model gpt-6-luna]      # one process per batch in batches.json
    python3 codex_agents.py <work_dir> review [--model gpt-5.6-terra]   # review_cases.json, ~10 per process
    python3 codex_agents.py <work_dir> ai     [--model gpt-5.6-terra]   # ai_cases.json, ~8 per process
    options: --pids p1 p2 ...  (override the list)   --jobs N  (max parallel, default 6)

Defaults are the newest Luna (cheap workers) and Terra (stronger reviewers) at the time of
writing. Pass --model when newer ones exist (`codex` -> /model lists them).
Each process runs sandboxed with write access limited to <work_dir>. Logs: <work_dir>/logs/.
"""
import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLES = {
    # role: (brief file, list source, chunk size, default model, reasoning effort)
    "worker": ("worker-prompt.md", "batches.json", None, "gpt-6-luna", "low"),
    "review": ("reviewer-prompt.md", "review_cases.json", 10, "gpt-5.6-terra", "medium"),
    "ai": ("ai-reviewer-prompt.md", "ai_cases.json", 8, "gpt-5.6-terra", "medium"),
}


def brief(role, work, pids):
    text = open(os.path.join(SKILL_DIR, "references", ROLES[role][0])).read()
    text = text.split("\n---\n", 1)[-1]          # the part meant for the agent
    cases = "\n".join(f"  - {p}" for p in pids)
    return (text.replace("{WORK_DIR}", work).replace("{SKILL_DIR}", SKILL_DIR)
                .replace("{PID_LIST}", ", ".join(pids)).replace("{CASES}", cases)
            + f"\n\nThe reasons for each case (if any) are in {work}/{ROLES[role][1]}. "
              "Paths may contain spaces: quote them.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("role", choices=ROLES)
    ap.add_argument("--model")
    ap.add_argument("--pids", nargs="*")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    work = os.path.abspath(a.work_dir)
    _, src, chunk, model, effort = ROLES[a.role]
    model = a.model or model

    if a.pids:
        groups = [a.pids[i:i + (chunk or 6)] for i in range(0, len(a.pids), chunk or 6)]
    else:
        data = json.load(open(os.path.join(work, src)))
        if isinstance(data, list) and data and isinstance(data[0], list):
            groups = data                                   # batches.json: already grouped
        else:
            ids = list(data)                                # dict (review) or list (ai) of pids
            groups = [ids[i:i + chunk] for i in range(0, len(ids), chunk)]
    os.makedirs(os.path.join(work, "logs"), exist_ok=True)

    def run(k_group):
        k, group = k_group
        log = os.path.join(work, "logs", f"{a.role}_{k}.log")
        cmd = ["codex", "exec", "-m", model, "-c", f'model_reasoning_effort="{effort}"',
               "-s", "workspace-write", "-C", work, "--skip-git-repo-check",
               "-o", os.path.join(work, "logs", f"{a.role}_{k}.last.txt"),
               brief(a.role, work, group)]
        with open(log, "w") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT).returncode
        return k, group, rc

    print(f"{a.role}: {len(groups)} codex processes on {model} (max {a.jobs} at once)")
    with ThreadPoolExecutor(a.jobs) as ex:
        for k, group, rc in ex.map(run, enumerate(groups)):
            print(f"  [{'ok' if rc == 0 else f'exit {rc}'}] {a.role}_{k}: {', '.join(group)}")
    missing = [p for g in groups for p in g if a.role == "worker" and not os.path.exists(os.path.join(work, "grades", f"{p}.json"))]
    if missing:
        print("  missing grade files (re-run with --pids):", " ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
