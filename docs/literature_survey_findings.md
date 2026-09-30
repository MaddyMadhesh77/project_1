# FINDINGS IN LITERATURE SURVEY

Status: v1 · 2026-08-18
Synthesizes [literature_review.md](literature_review.md)'s 24 papers into the
Gap Identification and Objective Framing material for RecoverMem's review.
Read the per-paper file first — this file assumes familiarity with each
citation and argues *across* them rather than re-summarizing any one paper.

---

## 1. What the survey as a whole shows

Three independent research threads converged on the same problem — LLM
agents with persistent memory can be poisoned — within roughly an
18-month window (2024 through mid-2026):

1. **Offensive work** (AgentPoison, MINJA, CorruptRAG, PoisonedRAG, Semantic
   Chameleon) proved the attack is practical, requires a small injection
   budget (as low as one document), and works even against agents holding
   pre-existing, legitimate memories.
2. **Defensive/architectural work** (MemLineage, MemAudit, A-MAC, TMA-NM,
   the Lin et al. survey) responded with increasingly sophisticated
   admission-control, auditing, and governance mechanisms.
3. **Adjacent foundational fields** (database recovery, data provenance,
   Merkle trees, Sybil-resistant reputation, machine unlearning,
   explainable AI, hybrid retrieval) supply the individual mechanisms the
   defensive papers above assemble, but none of those foundational papers
   were written with LLM memory poisoning in mind — they are being
   *repurposed*, not extended.

The single clearest finding across the whole survey: **every defensive
paper picks 1–2 of the mechanisms RecoverMem combines, not all of them.**
No paper in this survey combines write-time explainable admission scoring,
non-destructive versioning, cryptographic tamper-evidence, a derivation
graph, *and* graduated (not binary) dependency-aware rollback in one
system. That gap — not any single novel mechanism — is what Gap
Identification should center on.

---

## 2. Gap identification, mechanism by mechanism

| # | Mechanism | Closest prior work | What it does | What it's missing that RecoverMem has |
|---|---|---|---|---|
| G1 | Write-time trust gate | A-MAC (§1.5) | Interpretable 5-factor admission score | No versioning, no revisit if new evidence arrives later — the decision is final |
| G2 | Merkle + derivation-graph combo | MemLineage (§1.3) | Signed Merkle log + weighted DAG, binary refuse-gate | Refuse/allow only — no graded score, no review-queue middle state, no recovery once a poison is found (only prevention of *future* harm) |
| G3 | Post-hoc detection of poisoned memory | MemAudit (§1.4) | Causal attribution + structural anomaly detection | Detection only — no specified graduated recovery procedure for descendants once the culprit is found |
| G4 | Formal non-malleability | TMA-NM (§1.7) | Machine-checked, origin-bound authority; explicitly documents corroboration-laundering | Narrower deployment envelope, no interactive/demoable system; RecoverMem's own `corroboration_count` is *exactly* the attack surface this paper warns about, and RecoverMem does **not** yet close this gap either (see §5 below) |
| G5 | Selective/partial recovery | ARIES (§8.1) | Partial transaction rollback via write-ahead log | Operates on physical write-order, not semantic derivation — cannot express "this memory was *inferred from* that one" |
| G6 | Removing a poisoned data point's influence | Machine unlearning / Pawelczyk et al. (§8.2) | Approximate unlearning of a data point's effect on trained weights | **Proven not to fully work**, even at high compute budget — the literature-backed reason RecoverMem does not attempt implicit "unlearning" and instead does explicit graph re-validation |
| G7 | Security value of hybrid retrieval | Semantic Chameleon (§2.3) | Quantifies hybrid BM25+vector retrieval cutting a poisoning attack from 38%→0% | Only against *one* attack class (dense-only sleeper-trigger); an adaptive attacker jointly optimizing against both retrieval legs still gets 20–44% — hybrid retrieval is a partial, not complete, defense |
| G8 | Sybil/corroboration resistance | Cheng & Friedman (§6.1) | Proves *no symmetric* reputation function can be sybil-proof | This is a general impossibility result — it applies to RecoverMem's `corroboration_count` exactly as written today, and RecoverMem has no asymmetric or sybil-resistant alternative implemented |

Rows G1–G3 and G5–G7 are gaps in *other* systems that RecoverMem's design
addresses (this is the positive Gap Identification story). Rows G4 and G8
are gaps that remain **unresolved in RecoverMem itself** — these should be
presented candidly in the review, not omitted, because a reviewer who has
read TMA-NM or Cheng & Friedman will ask about them directly, and having
the answer ready ("yes, this is a known, literature-documented limitation
of the current MVP, here's what closing it would require") reads far
better than being caught unaware.

---

## 3. Positioning table (expanded from DESIGN.md §1)

| Work | Binary gate or graded score? | Versioning? | Tamper-evidence? | Dependency graph? | Rollback granularity | Corroboration-attack aware? |
|---|---|---|---|---|---|---|
| MemLineage | Binary refuse-gate | No | Yes (Merkle+signed log) | Yes (weighted DAG) | None (prevention only) | Not addressed |
| MemAudit | N/A (post-hoc audit) | No | No | Implicit (causal graph for attribution only) | Detection only, no recovery procedure specified | Not addressed |
| A-MAC | Graded (5-factor score) | No | No | No | N/A | Not addressed |
| TMA-NM | Formal non-malleable gate | No | Implicit (origin-bound) | No | None (prevention only) | **Explicitly addressed** — the strongest in the survey |
| Lin et al. survey | N/A (survey, no implementation) | Named as needed (Forget & Rollback phase) | Named as needed | Named as needed | Not instantiated | Named as a governance concern |
| **RecoverMem** | Graded score + review queue | **Yes** (git-style, non-destructive) | **Yes** (Merkle, per-write) | **Yes** (networkx DAG) | **Graduated per-node** (keep/revert/remove) | **Not yet** — known gap, see §2 row G8 |

This table is the direct, defensible answer to "what's novel here" —
RecoverMem is the only row with every column checked except the last one,
and the last one being unchecked is disclosed rather than hidden.

---

## 4. Design decisions the literature justifies (use in Design/Methodology)

- **Graded score + review queue, not a binary refuse-gate** — MemLineage
  (§1.3) shows a binary gate works but has no middle ground; A-MAC (§1.5)
  shows a graded, interpretable multi-factor score is achievable and
  benchmarkable. RecoverMem's store/review/reject three-way decision is a
  synthesis of both.
- **Explicit dependency-graph rollback, not implicit unlearning** —
  Pawelczyk et al. (§8.2) is direct, ICLR-2025-published evidence that the
  implicit alternative (approximate machine unlearning) provably fails to
  remove poisoning effects even with substantial compute. This is the
  strongest single justification in the whole survey for why RecoverMem's
  rollback engine does explicit BFS re-validation instead.
- **Hybrid (BM25 + dense) retrieval** — justified on *both* axes:
  Blended RAG (§2.4) for accuracy, Semantic Chameleon (§2.3) for security
  (38%→0% against one attack class, with the important caveat that an
  adaptive attacker still achieves 20–44%, which the review should state
  plainly rather than imply hybrid retrieval alone solves retrieval
  poisoning).
- **SHAP-based explainability, not an opaque classifier** — grounded in
  Lundberg & Lee's (§5.1) provably unique Shapley-value attribution
  properties, not merely "a popular library."
- **Reciprocal Rank Fusion for combining retrieval legs** — Cormack et al.
  (§9.1) is the direct algorithmic source; its core insight (fuse by rank,
  not raw score, because cosine similarity and tsvector rank are not on
  comparable scales) is the actual reason RRF is correct here, not just
  convention.
- **Non-destructive versioning coupled to a trust decision** — OrpheusDB
  (§7.1) is the systems-level precedent for git-style versioning of
  structured data, but versions unconditionally; RecoverMem's addition is
  gating each version's trust status at write time, which no citation in
  this survey does simultaneously with git-style versioning.

---

## 5. Honest limitations to state in the review (do not omit)

Reviewers respond far better to self-identified limitations backed by
citations than to a project that claims completeness. Four items, each
with a literature anchor:

1. **Corroboration-laundering is a known, unresolved attack against
   `corroboration_count`.** TMA-NM (§1.7) names this attack class directly;
   Cheng & Friedman's impossibility result (§6.1) proves it is not a
   fixable oversight but a structural property of any symmetric
   corroboration-counting scheme — closing this gap would require moving to
   an asymmetric, flow-based scoring function, which RecoverMem does not
   currently implement.
2. **Rule-engine weights are uncalibrated relative to the field's own
   standard.** The zero-trust access-control paper (§5.2) performs a
   sensitivity analysis of its scoring weights; RecoverMem's rule scorer
   has not undergone equivalent calibration (also flagged in the project's
   own code: the weights in `backend/app/core/config.py` are documented as
   hand-tuned, not calibrated against labelled data).
3. **Hybrid retrieval is a partial, not complete, defense against
   retrieval-time poisoning.** Semantic Chameleon (§2.3) shows an adaptive
   attacker who jointly optimizes against both the sparse and dense
   retrieval legs still achieves 20–44% co-retrieval success, so
   RecoverMem's layered design (hybrid retrieval *plus* trust scoring)
   should be presented as defense-in-depth, not as either layer being
   independently sufficient.
4. **A false *first* statement about a topic is structurally
   undetectable, and repeating it makes the eventual true correction the
   one that gets flagged instead.** Traced directly through
   `services/features.py` and `services/trust_engine.py`'s actual weights
   (not a hypothetical):
   - A brand-new false claim ("I love Python," no prior "Python" memory
     exists) hits `best_match is None` — `contradiction` and
     `corroboration_count` are hard-zeroed by construction
     ([features.py:96-106](../backend/app/services/features.py#L96-L106)),
     so it scores purely on `source(30) + novelty(24) + context(18) = 72`
     and is stored as current, indistinguishable from a true novel fact.
   - Repeating the same false claim later *raises* its trust further via
     `self_corroboration`
     ([trust_engine.py:66-72](../backend/app/services/trust_engine.py#L66-L72)):
     `source(30) + semantic_similarity(≈22.8) + corroboration(20) ≈ 90.8`.
   - When the true correction ("I hate Python") finally arrives, it is
     the one retrieval matches against the now-highly-trusted lie, and the
     contradiction penalty is *scaled up* by that prior trust
     (`trust_weight = 0.5 + 0.5 × prior_trust/100 ≈ 0.95`):
     `30 + 22.8 + 0 + 18 − 38.16 + 0 ≈ 32.6` — rejected/quarantined.

   This is the concrete, code-verified instance of the general
   corroboration-laundering weakness in item 1 above (TMA-NM §1.7,
   Cheng & Friedman §6.1): the trust engine has no ground-truth oracle,
   only internal consistency and repetition count, so "first to plant a
   claim, repeated a few times" beats "true," not just "beats
   undetected."

---

## 6. How to use this in the review presentation

- **Literature Review / Rationale [5]:** Open with Biggio et al. (§12.1,
  2012) to show "trust the input" is the oldest known ML-security failure
  mode, then Lin et al.'s lifecycle survey (§1.8) as the organizing
  framework, then the Youssef et al. position paper (§10.2) to show the
  same concern is recognized one layer down (model weights). This gives a
  14-year historical arc in three citations rather than starting the
  narrative at 2024.
- **Gap Identification [5]:** Use the positioning table in §3 above —
  walk the graders through each column, ending on the one unchecked cell
  (corroboration-attack awareness) as evidence of a genuinely-understood,
  not hand-waved, limitation.
- **Objective Framing [5]:** Frame each DESIGN.md §2 goal as directly
  answering one gap-table row (G1 → graded score with review queue, G5/G6
  → graduated dependency-aware rollback, G7 → hybrid retrieval as
  defense-in-depth, not a silver bullet).
- **Design / Methodology [10]:** Use §4 above section-by-section —
  every non-trivial design choice (graded gate, explicit rollback, hybrid
  retrieval, SHAP, RRF, versioning) gets a one-sentence literature
  justification, which is exactly what separates "we built this" from "we
  built this *because*."
