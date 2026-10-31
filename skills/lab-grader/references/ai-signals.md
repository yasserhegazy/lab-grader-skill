# Judging whether a report was AI-written

Purpose: give the TA a **flag with evidence**, never a verdict and never a grade change.
These students write in a second language (Arabic first). Clean English, good formatting
and a well-organised report are **not** evidence of AI. Students are allowed to be good.
Flag only when several signals point the same way, and always quote the evidence.

## Levels

- **none**: nothing beyond normal good work.
- **low**: one weak or medium signal. Recorded, not shown as a flag.
- **medium**: two or more medium signals, or one strong signal. TA should look.
- **high**: strong signal(s) plus supporting ones, e.g. fabricated results, or script-generated
  file plus generic text that ignores the student's own output.

## Strong signals

- **Results that don't come from the student's own run**: the text quotes values (IPs, port
  states, return codes, host counts) that contradict or don't appear in their screenshots, or
  "outputs" typed as text with no screenshot when screenshots were required.
- **Template/example values passed off as results**: the assignment's example host/subnet reported
  with no screenshot evidence. (A screenshot that really shows it is fine, since VirtualBox
  uses 192.168.56.x.)
- **Chat-assistant leftovers**: "Certainly!", "Here is your report", "As an AI", "I hope this helps",
  "[Your Name]", "[Insert screenshot here]", "replace with your actual IP", raw Markdown
  (`**bold**`, `### Heading`, ``` fences) printed in the PDF.
- **File produced by a script** (metadata `python-docx`, `reportlab`, `fpdf`; from `meta.json`
  flags `META_SCRIPT_GENERATED`). Students do not write Python to produce a Word report by hand;
  chat assistants do this all the time. Strong, but still a signal: combine it with the text.
- **Explaining things their evidence doesn't show**: long discussion of "filtered" and "timeouts"
  when their own output only has open/closed, in a way that reads like a generic answer to the
  assignment rather than to their results. (The assignment often explicitly says not to do this.)

- **Unedited AI draft text**: "from the user's screenshot", "Replace this placeholder",
  `[ INSERT SCREENSHOT HERE ]`, "do not invent target results" (instructions to the AI, left in).

## Beyond what the lab taught (TA's explicit rule)

Compare code *and* explanations against the lab handout and assignment (`lab_reference.txt`).
Functions, libraries, tool options, idioms (`if __name__`, argparse, threading, type hints,
error tables) or concepts the course never showed are a signal: students write what they
were taught. Weigh it by how far outside it is. One extra standard call that most of the class
also used (see `class_share` in ai_scan.json) is weak; several untaught techniques plus fluent
theory the course never covered is strong. Always name the construct and quote it.

## Proof (needed for the grade penalty)

`proven` means the *work* is not the student's own: results contradicting their screenshots,
outputs/tables for runs that never happened, unedited AI draft text, or printed code that cannot
produce the shown output. Wording, metadata and outside-the-lab code alone are never proof.

## Medium signals

- Uniform, textbook paragraphs that never mention the student's own values (their IP, their
  ports, their counts), while the screenshots show something specific.
- Code far beyond the lab template with tutorial-style comments on nearly every line, docstrings,
  type hints, argparse, banners, emoji in output. Compare against what the lab taught.
  (One call such as `os.strerror` to explain a return code is a small natural step and only a weak
  signal on its own, but still list it under outside-the-lab.)
- Inconsistent voice: captions/notes in broken English, but intro/analysis in polished
  native-style prose with phrases like "delve", "crucial", "robust", "comprehensive",
  "seamless", "it is worth noting", "In summary,", "plays a pivotal role", heavy em-dashes.
- Emoji or check-mark bullets in headings, "Key Takeaways" boxes, a structure mirroring a
  chat answer rather than the assignment's own section list.
- Everything is perfect except evidence: excellent theory, but screenshots missing, cropped
  to hide the terminal prompt, or not matching the text.

## Weak signals (never flag on these alone)

- Good grammar, clear structure, nice tables.
- Printed from a browser (`META_BROWSER_PRINT`), since Google Docs does this.
- Explanation closely follows the assignment wording (students copy the question's terms).
- Similar section headings to other students (the assignment dictates them).

## Writing the flag

`signals` = short, concrete, quotable items, e.g.
`"metadata author=python-docx"`, `"Analysis says port 80 open, screenshot img_04 shows closed"`,
`"Intro: 'This comprehensive analysis delves into...'; captions elsewhere in broken English"`.
Never write "seems AI" without the reason.
