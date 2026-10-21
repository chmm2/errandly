*(Edit the bracketed parts, then paste into the submission system or print on
department letterhead and sign.)*

[Date]

To the Editor-in-Chief, IEEE Access

Dear Editor,

We submit the manuscript **"Trust Without Receipts: Collusion-Aware Social Dispatch
and Price-Claim Assessment for Campus Errand Platforms"** for consideration as a
research article in IEEE Access.

Delivery platforms control expense fraud by checking claims against menus, catalogues
or receipts. A campus errand platform has none of these, so a runner's reported price
is the only record and fraud control must work by inference. The manuscript describes
Errandly, a working prototype built for this setting, and studies a problem its own
design creates: a dispatcher that prefers friends makes honest friend groups look like
collusion rings. We evaluate the controls by running the production code inside
simulated semesters on a 1,200-student campus, with 30 seeds per setting and 95%
confidence intervals. Collusion rings hidden in ordinary friend groups were invisible
to structure-only and money-only signals and poorly found by two graph-mining
baselines (F1 at most 0.48), but were found as money cycles among mutual friends
(F1 = 0.96). Testing each flagged group against an acceptance model fitted to logged
dispatch rounds removed most false flags caused by the router, and the full pipeline
reached F1 = 0.87 to 0.97 across five behavioural regimes. We also report what did not
work: a first version of the test that reused the router's own scores suppressed 146
of 149 coordinated-ring flags, and no test of this kind can separate honest
favour-trading from careful collusion. Several faults found by the evaluation were
fixed in the code, and the paper reports the behaviour before and after.

We believe the work fits IEEE Access because it combines a deployed-system design with
a reproducible evaluation that spans distributed systems, security and social networks.

The manuscript is original, has not been published, and is not under consideration
elsewhere. It extends work done for the authors' undergraduate project at Vellore
Institute of Technology; the project report is unpublished. All authors have approved
the submission. The authors declare no conflict of interest [and received no specific
funding for this work]. The authors used an AI writing and coding assistant (Claude,
Anthropic) to help draft and edit the text and to write the evaluation scripts; the
authors reviewed and verified all content, code and results. The code is available
at https://github.com/chmm2/errandly, and the datasets, raw results, run logs and
test report behind every table and figure are in its paper-artifacts folder,
https://github.com/chmm2/errandly/tree/feat/payments-fraud-detection/paper-artifacts
[add Zenodo DOI if created].

[Optional: suggested reviewers, with affiliations and e-mail addresses, who have no
conflict of interest with the authors.]

Thank you for considering our manuscript.

Sincerely,

[Corresponding author name], on behalf of all authors
School of Computer Science and Engineering
Vellore Institute of Technology, Vellore 632014, Tamil Nadu, India
[e-mail] · ORCID [iD]
