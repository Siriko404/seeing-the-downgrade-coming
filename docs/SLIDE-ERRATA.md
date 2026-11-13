# Slide errata

`deck/lecture-slides.pdf` shows the slides as they were presented on 11 November 2026, minus three slides about the
fund's own holdings. These corrections apply to them. The last page of the PDF repeats this list.

| Page | On the slide | Correct |
|---|---|---|
| 4 | The agent "pulls ratings from EDGAR and SEDAR+ filings". | The agent fetches SEC (EDGAR) filings itself. For a company that files only in Canada on SEDAR+, you download the filing yourself and give the tool the file. |
| 4 | "writes a sourced briefing for every flagged company" | With this package the agent writes a note for any SEC filer you name, or for a Canadian firm from a filing you download. The trained model that flags companies is not included (see the README). |
| 8 | "Drag the field to try a simple top share." | This works only in the live web version of the slides, not in the PDF. |
| 9 | "fly whole brain · shuffled 0.781-0.806" | The upper end is 0.807 (0.806538 before rounding). |
| 10 | Malone, Smales & Liu 2026: "logit 0.536" | It is an ordered logit (0.536). |
| 12 | The SKILL.md rules shown | These are the rules as they were on the day. The SKILL.md in this package is a later version (it no longer mentions a rehearsal folder). |
| 13 | The box labelled "rows.json, written by the AI" | It shows the row after the checking code changed it. The AI had written the action as "outlook change"; the code renamed it "watch placed". |
| 14 | Step 4 is called WRITE. | The package's documents call it FINISH. Same step: code writes the note. |
| 15 | "The score runs only on the presenter's laptop." | In this package, the model's code is in `model/`, but the trained model, its licensed training data and its scores are not included, so a note shows no model score. |
