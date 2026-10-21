# Getting the Errandly paper submitted

This is the checklist for `docs/paper/ieee/main.pdf`. Nobody can promise acceptance.
What gets a paper through review is a clear claim, evidence that supports it, honest
limitations and correct formatting. The paper now has the first three. This guide
covers the rest, and the parts only the authors can do.

---

## 1. What only you can do (before anything else)

1. **Read every sentence and make sure all four authors can defend it.** Reviewers and
   your faculty will ask why a constant is 0.55, or why a cycle is suspicious when it
   is zero-sum. The answers are in Sections IV and VI. If a sentence does not sound
   like you, rewrite it in your own words. That is also the honest way to make the
   text yours.
2. **Disclose the AI assistance somewhere IEEE will see it.** At the faculty's
   request the sentence was taken out of the Acknowledgment, and the disclosure now
   sits in the cover letter; declare it in the submission form as well. Be aware that
   IEEE's policy asks for the disclosure in the acknowledgments section of the article
   itself, so an editor may ask you to put it back; raise this with your guide before
   submitting. IEEE requires that use of AI-generated text, figures or code be
   disclosed, naming the tool and what it was used for ([IEEE author guidelines on AI-generated text](https://open.ieee.org/author-guidelines-for-artificial-intelligence-ai-generated-text/)).
   The IEEE Access checklist repeats it ([IEEE Access submission checklist](https://ieeeaccess.ieee.org/wp-content/uploads/2025/09/IEEE-Access-Submission-Checklist.pdf)).
   Do not drop the disclosure altogether or try to disguise AI-assisted text with
   paraphrasing tools. Undisclosed use can lead to rejection or a later retraction, and paraphrasers
   introduce errors. If you rewrite large parts yourselves, update the statement so it
   describes what the assistant actually did.
3. **Confirm the author list and order with Dr. Ranjithkumar S.** The draft lists
   Chris Martin Mattam, Ujjwal Gogoi, Sanskriti Sajlal and Ranjithkumar S, in the order
   of the earlier draft. Decide the corresponding author (usually the guide) and add
   that person's e-mail to the `\thanks{}` line in `main.tex`.
4. **Check your own lines.** Each author should read their sentence in the Author
   Contributions section and their biography at the end of `main.tex`. The bios give
   only degree and affiliation; add research interests if the journal or your guide
   asks for them. IEEE Access requires biographies for all
   authors at submission ([submission guidelines](https://ieeeaccess.ieee.org/authors/submission-guidelines/)).
5. **Create ORCID iDs.** The submitting author must have a public, populated ORCID
   linked to their account (checklist above). Get one for every author anyway.
6. **Run a similarity check through the VIT library** (Turnitin or iThenticate). IEEE
   screens submissions with Crossref Similarity Check, which is iThenticate. IEEE
   publishes no single pass mark, and a score is not a verdict, so aim low: keep the
   overall score well under 15% excluding references, with no large block matching
   any one source. UGC's 2018 plagiarism regulations treat up to 10% as minor for
   theses, which is a sensible target here too. Expect matches against your own
   Project-I report and `docs/PAPER.md`; that is your own unpublished work, and the
   cover letter says so.
7. **Push the experiment code.** The paper says every number can be regenerated. That
   is only true once `backend/evals/paper/` and `docs/paper/` are committed and pushed
   to [github.com/chmm2/errandly](https://github.com/chmm2/errandly). A Zenodo release
   gives it a citable DOI for the code-availability statement.
8. **Know the six code fixes.** Section V lists six faults the first evaluation found
   (claim renaming, the router-score policy test, the zero-variance case, unwidened
   tier-0 errands, the 50-ring cap, and automatic suspension). All six are fixed in
   the code with regression tests, and Section VI reports before and after where it
   can be measured. A reviewer may ask about them; they are a strength, not a
   weakness.

---

## 2. Choosing where to send it

| Option | Fit | Cost | Notes |
|---|---|---|---|
| **IEEE Access** (journal, open access) | Good: broad, multidisciplinary, values working systems with honest evaluation | APC US$2,160; 20% off for IEEE society members, 5% for IEEE members ([APC page](https://ieeeaccess.ieee.org/about/article-processing-charges/)) | Binary accept/reject, about 4 weeks to a decision, at least two reviewers, about 27% acceptance ([rapid review](https://ieeeaccess.ieee.org/about/rapid-peer-review/)) |
| An IEEE Transactions journal (for example on computational social systems, or dependable and secure computing) | Topic fits | No APC for traditional publication | Much harder. Reviewers will ask for real pilot data. Better as a second paper after a pilot. |
| A Scopus-indexed IEEE conference | Good for a first publication | Registration fee | Usually 6 pages: cut to the problem, Sections IV-E/IV-F, Tables IV and VI, and Fig. 7. |

**Recommendation.** If the faculty requirement is a journal, IEEE Access is the
realistic target for this paper as it stands. Ask the VIT library whether the
institution has an IEEE open-access agreement or APC support, and whether your
department requires Scopus or Web of Science indexing (IEEE Access is indexed in
both). Avoid any "journal" that promises acceptance within days for a fee; check a
venue on Scopus Sources before submitting.

---

## 3. Formatting for IEEE Access

The paper is written in the standard IEEEtran journal class. IEEE Access requires
its own template ([submission guidelines](https://ieeeaccess.ieee.org/authors/submission-guidelines/)),
so before submitting:

1. Download the official IEEE Access LaTeX template from the submission guidelines
   page (Overleaf copies may be out of date).
2. Move the content across: title, abstract, index terms, every `\section`, the
   figures, `refs.bib`, the acknowledgment and the biographies. Nothing in the content
   needs to change.
3. Submit both the source (LaTeX or Word) and a matching PDF, under 40 MB in total.
4. The abstract is one paragraph of about 240 words; keep it under 250.
5. After acceptance you will need author photos and a graphical abstract: a figure from
   the paper, 660 x 295 pixels, JPG, under 45 KB ([post-acceptance guide](https://ieeeaccess.ieee.org/authors/post-acceptance-guide/)).
   Fig. 3 (architecture) or Fig. 7 (the z-distribution) would work.

If you go to a conference instead, use the IEEE conference template and the venue's
page limit.

---

## 4. The submission package

- [ ] Manuscript PDF, and the source in the journal's template
- [ ] Cover letter (`docs/paper/cover-letter.md`, edit and sign)
- [ ] All authors' names, affiliations and e-mails; corresponding author marked
- [ ] ORCID for the submitting author (preferably all)
- [ ] Biographies for every author (photos at final submission)
- [ ] AI-use disclosure in the Acknowledgment
- [ ] Code availability: repository URL (and Zenodo DOI if made)
- [ ] Conflict-of-interest statement (none, unless a sponsor exists)
- [ ] Funding statement (none, unless the project had a grant)
- [ ] Similarity report checked by your guide
- [ ] Open-access licence choice and copyright form, at acceptance

---

## 5. What reviewers will push on, and where the paper answers

| Likely question | Where it is answered | What would make it stronger |
|---|---|---|
| "All of this is simulated." | VI-A, VII-C say so plainly; production code runs inside the simulation; the simulator's closure and circulation match the production Cypher exactly | A small pilot with ethics approval, even one hostel for a month |
| "The thresholds are hand-picked." | Table III lists them; Section VI sweeps the ones that matter | Fit them from the pilot's offer log |
| "Your baselines are weak." | Table VI: single-signal baselines, an any-pair cycle search, FRAUDAR-style peeling and label propagation, the last two given the true ring size | Learned graph detectors once real labelled data exist |
| "Is the simulator tuned to make you look good?" | The paper reports where the design fails: the first policy test, the identifiability limit with honest favours, adaptive rings that farm little, the breadth attack, shops with few reporters, the unpriced-line swap | Have someone outside the team pick one behavioural setting before seeing results |
| "Is this new?" | Table I and the contribution list | Be ready to say in two sentences what is new: a social dispatcher and a collusion detector interfere, and the detector must be conditioned on a fitted model of the dispatcher's effect, not on its design weights |
| "Error bars?" | 30 seeds for main results and 10 per sweep point, with 95% confidence intervals; Table IV collects them; per-trial values are in `paper-artifacts/results/*.json` | Nothing more needed for a simulation study |
| "Ethics and privacy?" | VII-D and IV-B: automation may warn, demote and pause, but account suspension needs upheld flags; every flag carries its evidence; dismissal lifts the pause; local model; ethics approval before a pilot | Get the approval letter before the pilot, not after |

---

## 6. Rebuilding the paper and the numbers

Compile the PDF (either way works):

- **Overleaf:** zip the `docs/paper/ieee/` folder, upload it as a new project, set
  the main file to `main.tex` and the compiler to pdfLaTeX.
- **Locally:** `tectonic main.tex` inside `docs/paper/ieee/`.

Regenerate the experiments and figures: see `backend/evals/paper/README.md`. With 30
seeds the full set takes about 3 hours on a 16-thread laptop when the collusion parts
run in parallel, each against its own throwaway Neo4j; run the timing experiment
(`exp8`) alone.

---

## 7. A realistic timeline

| Week | Work |
|---|---|
| 1 | Each author revises two or three sections in their own words; guide reviews |
| 2 | Similarity check; move to the IEEE Access template; cover letter; push the code |
| 3 | Submit |
| about 4 weeks later | Decision. If rejected, use the reviews, revise and submit elsewhere |
