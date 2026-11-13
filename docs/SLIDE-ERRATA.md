# Slide errata

`deck/lecture-slides.pdf` shows the slides as they were presented on 11 November 2026, minus three slides about the
fund's own holdings, except pages 9 and 11, which were redrawn on 13 November 2026 with the rerun model comparison
(see `docs/RESULTS.md`). These corrections apply to the slides. The last page of the PDF repeats this list.

| Page | On the slide | Correct |
|---|---|---|
| 4 | The agent "pulls ratings from EDGAR and SEDAR+ filings". | The agent fetches SEC (EDGAR) filings itself. For a company that files only in Canada on SEDAR+, you download the filing yourself and give the tool the file. |
| 4 | "writes a sourced briefing for every flagged company" | With this package the agent writes a note for any SEC filer you name, or for a Canadian firm from a filing you download. The trained model that flags companies is not included (see the README). |
| 8 | "Drag the field to try a simple top share." | This works only in the live web version of the slides, not in the PDF. |
| 9 | The engine comparison | Redrawn with the 13 November 2026 rerun (fixed row order). On 11 November the slide showed single engines 0.787-0.795, averages 0.809 and an edge of 0.007, and the subtitle "One fancier engine edges ahead by 0.007, too little to matter; the simple logit stays." |
| 10 | Malone, Smales & Liu 2026: "logit 0.536" | It is an ordered logit (0.536). |
| 11 | The line "fancier: a 0.007 edge at most" | Redrawn with the rerun: "fancier: averages ahead by up to 0.014". |
| 12 | The SKILL.md rules shown | These are the rules as they were on the day. The SKILL.md in this package is a later version (it no longer mentions a rehearsal folder). |
| 13 | The box labelled "rows.json, written by the AI" | It shows the row after the checking code changed it. The AI had written the action as "outlook change"; the code renamed it "watch placed". |
| 14 | Step 4 is called WRITE. | The package's documents call it FINISH. Same step: code writes the note. |
| 15 | "The score runs only on the presenter's laptop." | In this package, the model's code is in `model/`, but the trained model, its licensed training data and its scores are not included, so a note shows no model score. |
