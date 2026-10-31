#!/usr/bin/env python3
"""Build a browser script that fills Moodle's quick-grading page from grades.csv.

Usage:
    python3 moodle_fill.py <work_dir> [--max-grade 11] [--only <pid> ...]

Writes <work_dir>/moodle_fill.js. Run it on the assignment's "Submissions" page (Quick grading on,
all students on one page) through the browser tool's JavaScript runner, or paste it into the
DevTools console. It:
  - matches each table row to a student by the University "User ID" column (falls back to the
    full name when the report had no id),
  - fills the grade box and the "Feedback comments" box, firing input/change events,
  - never clicks Save: the TA checks the page and saves,
  - returns a report: filled, not found on the page, page rows with no grade, grades above
    the Moodle maximum (skipped), and Moodle's own "late" text per filled student so it can be
    compared with the late penalty in grades.csv.
"""
import argparse
import csv
import json
import os

JS = r"""
(() => {
  const DATA = __DATA__;
  const MAX = __MAX__;
  const norm = s => (s || "").replace(/\s+/g, " ").trim();
  const byId = {}, byName = {};
  for (const d of DATA) { if (d.sid) byId[d.sid] = d; byName[norm(d.name)] = d; }
  const rows = [...document.querySelectorAll("table tbody tr")];
  const report = {filled: [], skipped_over_max: [], page_rows_without_grade: [], late_on_moodle: []};
  const used = new Set();
  const set = (el, v) => {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, v);
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  };
  for (const tr of rows) {
    const grade = tr.querySelector('input[name^="quickgrade_"]:not([name*="comments"]), input[id^="quickgrade_"]:not([id*="comments"])');
    const fb = tr.querySelector('textarea[name^="quickgrade_comments"], textarea[id^="quickgrade_comments"]');
    if (!grade) continue;
    const cells = [...tr.cells].map(c => norm(c.innerText));
    let d = null;
    for (const c of cells) { if (byId[c]) { d = byId[c]; break; } }
    if (!d) {
      const link = tr.querySelector('a[href*="user/view.php"], a[href*="user/profile.php"]');
      if (link && byName[norm(link.innerText)]) d = byName[norm(link.innerText)];
    }
    const label = cells.find(c => /^\d{7,10}$/.test(c)) || norm((tr.querySelector("a") || {}).innerText);
    if (!d) { report.page_rows_without_grade.push(label); continue; }
    used.add(d.pid);
    if (MAX && d.grade > MAX) { report.skipped_over_max.push(`${d.sid || d.name}: ${d.grade}`); continue; }
    set(grade, String(d.grade));
    if (fb) set(fb, d.feedback);
    report.filled.push(`${d.sid || d.name}: ${d.grade}`);
    const late = cells.find(c => /late/i.test(c) && /(day|hour|min)/i.test(c));
    if (late) report.late_on_moodle.push(`${d.sid || d.name}: ${late} | our late penalty: ${d.late}`);
  }
  report.not_found_on_page = DATA.filter(d => !used.has(d.pid)).map(d => `${d.pid} ${d.sid} ${d.name}`);
  report.summary = `filled ${report.filled.length}/${DATA.length}; NOT SAVED - check the page, then click "Save all quick grading changes"`;
  return JSON.stringify(report, null, 1);
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--max-grade", type=float, default=None, help="Moodle's maximum grade (e.g. 11); higher grades are skipped")
    ap.add_argument("--only", nargs="*", help="participant ids to fill (default: everyone)")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(os.path.join(a.work_dir, "grades.csv"), encoding="utf-8-sig")))
    if a.only:
        rows = [r for r in rows if r["participant_id"] in a.only]
    data = [{"pid": r["participant_id"], "sid": r.get("student_id", ""), "name": r["name"],
             "grade": float(r["grade_10"]), "feedback": r.get("feedback_ar", ""),
             "late": r.get("late_penalty", "0")} for r in rows]
    js = JS.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace(
        "__MAX__", json.dumps(a.max_grade))
    out = os.path.join(a.work_dir, "moodle_fill.js")
    open(out, "w", encoding="utf-8").write(js)
    no_id = [d["pid"] for d in data if not d["sid"]]
    print(f"{out}: {len(data)} students" + (f" | no university id (matched by name): {', '.join(no_id)}" if no_id else ""))


if __name__ == "__main__":
    main()
