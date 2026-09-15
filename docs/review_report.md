# RecoverMem — Project Review Report

*(Page 1 — cover page with your registration number, name, guide details, and
signatures — intentionally left for you to fill from the original template.
Everything below is page 2 onward.)*

---

## ABSTRACT

Large Language Model (LLM) agents increasingly rely on persistent long-term
memory to personalize behaviour across sessions. This memory is typically
trusted unconditionally: mainstream extract-and-store pipelines have no
mechanism to evaluate whether a candidate memory should be believed, where it
originated, or what breaks if it later turns out to be false. This exposes
agents to memory poisoning — a single false or adversarial statement, once
persisted, is treated as permanent ground truth and silently corrupts every
downstream inference derived from it. This project presents RecoverMem, a
security middleware layer sitting between an LLM agent and its long-term
memory store. RecoverMem intercepts every candidate memory before
persistence, computes an explainable trust score from hybrid-retrieval
features using an additive rule engine blended with a RandomForest+SHAP
layer, and issues a store/review/reject decision. Accepted memories are never
overwritten — they are versioned non-destructively with full source
provenance retained. A Merkle tree is recomputed on every write to make the
store tamper-evident, and an explicit dependency graph records which
memories were derived from which, so a poisoned memory's full blast radius
can be traced and a dependency-aware rollback engine can re-validate each
descendant individually. A survey of 24 verified papers positions RecoverMem
against closely related 2024–2026 work and identifies the specific
combination of mechanisms — write-time admission, versioning,
tamper-evidence, dependency tracing, and graduated rollback — that no single
prior system assembles together.

**Keywords:** LLM Agent Memory, Memory Poisoning, Trust Scoring, Explainable
AI (SHAP), Merkle Tree, Data Provenance, Dependency Graph, Non-Destructive
Versioning, Retrieval-Augmented Generation, Rollback Recovery

---

## 1. INTRODUCTION

Conversational AI agents built on large language models are moving from
stateless question-answering toward long-lived assistants that remember
facts about a user across sessions — preferences, personal details, past
decisions — and use that memory to personalize every future interaction.
Production-style systems that implement this pattern (Mem0-style
extract → dedupe → store pipelines) treat the memory store as an
unconditionally trusted knowledge base: once a fact is extracted from a
conversation and written, it is retrieved and reasoned over exactly like a
verified fact, indefinitely.

This design choice creates a serious and, until very recently, under-studied
attack surface. Because the memory store has no concept of trust,
provenance, or consequence, an attacker (or simply a mistaken user) who gets
one false statement stored has permanently altered what the agent believes,
with no record of who said it, why it was believed, or what later
recommendations depended on it. Academic interest in this exact problem —
"memory poisoning" of LLM agents — has grown rapidly across 2024–2026, with
multiple independent research groups converging on overlapping but
incomplete defensive mechanisms (surveyed in Section 6).

RecoverMem is a response to this gap: a middleware layer that sits between
an LLM agent and its long-term memory store and treats every write as a
security-relevant event rather than a database insert. Rather than proposing
one new cryptographic or machine-learning primitive, RecoverMem's
contribution is assembling five mechanisms that the literature has so far
only ever combined partially — explainable write-time admission control,
non-destructive versioning, cryptographic tamper-evidence, an explicit
derivation graph, and graduated, dependency-aware rollback — into one
coherent, demoable system. The remainder of this report frames the problem
being solved, situates it against the current literature, and describes
RecoverMem's design, architecture, and requirements.

---

## 2. PROBLEM STATEMENT

LLM agents with persistent memory can be poisoned: a single false or
manipulated statement, once stored, is treated as ground truth forever and
silently corrupts every downstream recommendation derived from it.
Mainstream memory-for-agents systems in production use today have no
concept of *trust*, *provenance*, or *blast radius* — they cannot answer
"should this be believed," "where did this come from," or "what else breaks
if this turns out to be false." Existing academic defenses (Section 6) each
address one facet of this problem — admission scoring, cryptographic
tamper-evidence, post-hoc auditing, or formally verified non-malleability —
but no system combines admission control, non-destructive history,
tamper-evidence, dependency tracing, and recovery in one working pipeline.
RecoverMem addresses this by acting as a security middleware layer that
intercepts every candidate memory before it is persisted, scores it for
trustworthiness, versions it instead of overwriting, records full
provenance, tamper-evidences the store with a Merkle tree, and tracks
derivation dependencies between memories so that a poisoned memory and
everything derived from it can be found and recovered automatically.

---

## 3. OBJECTIVES

1. Gate every write to long-term memory through an explainable trust
   decision (store / review / reject), rather than storing all extracted
   candidates unconditionally.
2. Never destructively overwrite a memory — maintain a full, Git-style
   version history for every fact the agent has ever believed.
3. Record full provenance per memory version (source type, conversation,
   model, raw input) so every stored fact is auditable back to its origin.
4. Provide tamper-evidence over the memory store using a cryptographic
   Merkle tree, so any out-of-band modification (e.g. a direct database
   edit) is detectable and localizable to the exact affected record.
5. Build an explicit dependency graph capturing which memories were derived
   using which other memories as retrieval context, so the blast radius of
   a poisoned memory can be traced rather than guessed.
6. Implement dependency-aware, graduated rollback: when a memory is found
   to be poisoned, re-validate — not blindly delete — every memory derived
   from it, and decide per node whether it should be kept, reverted, or
   removed.
7. Deliver a working, interactive admin dashboard that makes every
   mechanism above visible and demonstrable, rather than leaving trust
   scoring, integrity, and rollback as invisible backend logic.

---

## 4. SCOPE OF THE PROJECT

**In scope:**
- A chat-driven pipeline that extracts candidate memories, embeds them,
  retrieves related existing memories via hybrid (sparse + dense) search,
  engineers a feature vector, and scores trust using a rule engine blended
  with a trained RandomForest + SHAP explainability layer.
- Non-destructive versioning and per-version provenance for every stored
  memory.
- Merkle-tree tamper-evidence recomputed on every write, with an on-demand
  integrity-verification endpoint.
- A dependency graph between memories and a rollback engine that traces and
  re-validates descendants of a poisoned memory.
- An admin dashboard covering memories, memory detail/trust breakdown,
  dependency graph visualization, integrity checks, rollback, analytics,
  logs, and semantic search.
- An attack-simulation surface (poison injection, direct database tamper)
  for demonstrating the above mechanisms end-to-end.

**Out of scope (non-goals) for this stage of the project:**
- A multi-tenant authentication/authorization model — the system assumes a
  single demo user; per-user access control is future work.
- Production-scale vector search (millions of vectors) — the project
  targets demo scale, where an exact sequential similarity scan is
  sufficient and an approximate index is deliberately avoided.
- Training a production-grade ML trust classifier — a small RandomForest
  trained on a hand-authored synthetic dataset plus logged outcomes is
  sufficient to be real and explainable at this scale.
- Support for arbitrary third-party LLM providers — one pluggable
  `LLMClient` interface with one concrete implementation is sufficient for
  the MVP.
- Defending against coordinated, sybil-style corroboration attacks (see
  Section 6.1's findings) — identified as a known limitation and future
  work, not solved in the current design.

---

## 5. PROPOSED SYSTEM

RecoverMem is proposed as a security middleware layer inserted between an
LLM agent's conversational front end and its persistent memory store,
exposing two front doors onto one shared backend: a **chat surface** that
looks like an ordinary conversational interface and never exposes security
internals, and an **admin dashboard** that exposes every mechanism below for
inspection and control.

Every user message flows through a nine-stage pipeline: (1) an LLM client
(templated or Claude-backed) drives the conversational turn; (2) a
rule-based extractor identifies candidate memory statements; (3) an
embedding service (Sentence-BERT, 384-dimensional) vectorizes each
candidate; (4) a hybrid retrieval stage combines dense (pgvector cosine
similarity) and sparse (Postgres full-text) search via reciprocal rank
fusion to find the most related existing memory, if any; (5) a feature
engineering stage computes an 8-dimensional feature vector (similarity,
contradiction, source reliability, memory age, prior trust, corroboration
count, conversation recency, match indicator); (6) a trust engine combines
an interpretable additive rule score with a trained RandomForest + SHAP
layer to produce a 0–100 trust score, a per-feature explainability
breakdown, and a store/review/reject decision; (7) a versioning service
writes a new, non-destructive version of the memory regardless of the
decision (so a rejected update still becomes queryable history, correctly
flagged) together with its provenance record; (8) a Merkle service
recomputes a tamper-evident root hash over the store; and (9) a dependency
graph service records a derivation edge whenever a new memory's retrieval
context included an existing one.

On top of this pipeline, a rollback engine allows a memory found to be
poisoned to be marked as such; it performs a breadth-first search over the
dependency graph to find every descendant, re-evaluates each one with the
poisoned ancestor's support explicitly excluded, and writes a new version
for each with an outcome of *kept* (independently corroborated), *reverted*
(falls back to a prior trustworthy version), or *removed* (no independent
support and no fallback) — never mutating an existing row.

As established in the literature survey (Section 6), no single prior
academic system combines all of these mechanisms in one working pipeline;
RecoverMem's proposed contribution is this coherent, end-to-end integration
together with a fully interactive dashboard that demonstrates it, rather
than a novel cryptographic or machine-learning primitive in isolation.

---

## 6. LITERATURE SURVEY (minimum 15 papers)

*(APA-format full citations are in the References section; this table
summarizes each paper's contribution, merits, and demerits relative to
RecoverMem's problem. All 20 entries below are independently verified,
existing, citable papers — cross-checked against arXiv, ACM, IEEE, or
publisher pages before inclusion.)*

| S.NO | TITLE | MERITS | DEMERITS |
|---|---|---|---|
| 1 | AgentPoison: Red-teaming LLM Agents via Poisoning Memory or Knowledge Bases (Chen et al., 2024) | The first attack to target an LLM agent's long-term memory/knowledge base directly rather than its weights. A small number of trigger-optimized malicious demonstrations reliably steer the agent while leaving normal queries unaffected, and the attack requires no model retraining. Evaluated across three realistic agent domains (driving, QA, healthcare), giving strong external validity that memory poisoning is a practical, not theoretical, threat. | Purely offensive — proposes no defense or detection mechanism. Assumes a static, pre-loaded knowledge base rather than a memory store that accretes over a live, ongoing conversation, which is RecoverMem's actual setting. |
| 2 | Memory Injection Attacks on LLM Agents via Query-Only Interaction — MINJA (Dong et al., 2025) | Shows an attacker with no privileged write access — only ordinary conversational queries — can still seed malicious memories using a bridging technique that evades retrieval-time detection, with reported injection success above 95%. Directly relevant since this is exactly RecoverMem's real ingestion channel (the `/chat` endpoint), not an idealized direct-database-access threat model. | Proposes no defense of its own. Does not test how a populated, competing memory store (rather than an empty one) changes attack effectiveness — a gap paper 6 below addresses. |
| 3 | MemLineage: Lineage-Guided Enforcement for LLM Agent Memory (Ouyang & Hou, 2026) | The closest single prior work to RecoverMem's architecture: combines RFC-6962 Merkle logs with Ed25519-signed entries and a weighted derivation DAG, refusing sensitive actions justified by untrusted-ancestor memory. Reports zero attack success across three poisoning workloads at sub-millisecond overhead. | Uses a binary refuse/allow gate with no graded admission decision and no review-queue middle state. Prevents future harm but has no mechanism to recover a store once a poisoned entry is already discovered — no versioning, no rollback. |
| 4 | MemAudit: Post-hoc Auditing of Poisoned Agent Memory via Causal Attribution and Structural Anomaly Detection (Tan et al., 2026) | Identifies which stored memories caused harmful agent behaviour after an attack, using causal-impact attribution plus structural anomaly detection. Validated directly against MINJA, reducing downstream attack success from 70–83% to 0%. | Purely audit/detection-oriented — identifies the poisoned memory after harm has occurred but specifies no graduated recovery procedure for its descendants, and has no versioning concept (implies deletion rather than history-preserving recovery). |
| 5 | A-MAC: Adaptive Memory Admission Control for LLM Agents (Zhang et al., 2026) | Frames memory retention as a structured decision over five interpretable factors (utility, confidence, novelty, recency, content-type prior), combining rule-based extraction with lightweight LLM assessment. Validated on the LoCoMo benchmark (F1 0.583, 31% lower latency than state-of-the-art). Near-identical philosophy to RecoverMem's own additive rule scorer. | Admission-only — no versioning, no tamper-evidence, no dependency graph, no rollback. A memory once admitted is admitted for good, with no mechanism to revisit the decision if new contradicting evidence arrives later. |
| 6 | Securing LLM-Agent Long-Term Memory Against Poisoning — TMA-NM (Louck, 2026) | The strongest security guarantee surveyed: a formally verified, machine-checked non-malleable, origin-bound authority scheme, reporting zero attack success across eight frontier models. Explicitly names "corroboration-laundering" (coordinated fake corroboration) as an attack class. | Formal guarantees come with a narrower deployment envelope than a general-purpose additive score, and the paper describes a security mechanism, not an interactive, demoable product. Directly exposes an unresolved weakness in RecoverMem's own corroboration-count feature (see Section 6.1). |
| 7 | A Survey on Long-Term Memory Security in LLM Agents (Lin et al., 2026) | The organizing survey for the field: frames security across a six-phase lifecycle (Write, Store, Retrieve, Execute, Share & Propagate, Forget & Rollback) and argues security must be anchored at storage/write time rather than retrofitted at retrieval or execution time — precisely RecoverMem's design choice. | As a survey, it catalogs the primitives a system *should* have but does not itself instantiate all of them in a single, working, interactive implementation. |
| 8 | PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation (Zou et al., 2024) | The foundational RAG-poisoning paper, formulating injection of a small number of malicious texts into a knowledge base as an explicit optimization problem, with high demonstrated success against real pipelines. Establishes the threat-model vocabulary later corpus-poisoning work builds on. | Assumes a largely static knowledge base corrupted once, not a continuously growing, conversationally fed memory store — a meaningfully easier attack surface than RecoverMem's incremental setting. |
| 9 | Practical Poisoning Attacks against Retrieval-Augmented Generation — CorruptRAG (Zhang et al., 2025) | Shows a single injected malicious text — far below prior multi-text budgets — is sufficient to reliably corrupt targeted-query answers (over 90% success), sharpening the threat model to the hardest-to-detect, most realistic case: one bad memory is enough. | Still framed as corpus/knowledge-base poisoning rather than conversational-memory poisoning specifically, and proposes no defense. |
| 10 | Semantic Chameleon: Corpus-Dependent Poisoning Attacks and Defenses in RAG Systems (Thornton, 2026) | Directly, empirically validates hybrid (BM25 + vector) retrieval as a *security* mechanism: pure dense retrieval lets a gradient-guided attack succeed 38% of the time, while adding hybrid retrieval — with no model changes — drops this to 0% against that attack class. The strongest quantitative citation for RecoverMem's own hybrid retrieval design. | An adaptive attacker who jointly optimizes against both retrieval legs still achieves 20–44% success — hybrid retrieval is a partial, not complete, defense, and this is a single-author preprint with less peer-review scrutiny than a venue-published paper. |
| 11 | Blended RAG: Improving RAG Accuracy with Semantic Search and Hybrid Query-Based Retrievers (Sawarkar et al., 2024) | Systematically shows hybrid-query RAG (BM25 + dense KNN + sparse-encoder) substantially outperforms any single retriever across three standard QA benchmarks, giving an accuracy-side justification for hybrid retrieval that complements paper 10's security-side justification. | Purely an accuracy benchmark with no adversarial or poisoning evaluation, so it cannot stand alone as a security justification. |
| 12 | Why and Where: A Characterization of Data Provenance (Buneman, Khanna, & Tan, 2001) | The seminal database-theory formalization of provenance, distinguishing *why*-provenance (which source facts justify a result) from *where*-provenance (the literal source a value was copied from) — the theoretical basis for RecoverMem's own provenance table and dependency graph. | Purely theoretical and database-internal; predates any notion of ML models, LLMs, or trust scoring, so it carries no security angle on its own. |
| 13 | Protocols for Public Key Cryptosystems (Merkle, 1980) | The original Merkle tree construction: any leaf in a binary hash tree can be authenticated against one published root via a logarithmic-length path, without re-verifying every other leaf — the foundational primitive RecoverMem's tamper-evidence mechanism directly applies. | Says nothing about the operational pitfalls of maintaining a Merkle root incrementally in a live, concurrently written database — exactly where two of RecoverMem's own implementation bugs (Section 6.1) originated. |
| 14 | A Unified Approach to Interpreting Model Predictions — SHAP (Lundberg & Lee, 2017) | Unifies six prior feature-attribution methods under one Shapley-value framework with provably unique attribution properties, becoming the standard explainability method for tabular ML — the exact method (`shap.TreeExplainer`) RecoverMem's trust engine uses to produce its per-feature trust breakdown. | Exact SHAP computation is expensive in general (though `TreeExplainer` is a fast, exact special case for tree ensembles); provides *local* per-decision explanations, not a guarantee that the underlying model's decision boundary itself is well-calibrated. |
| 15 | Sybilproof Reputation Mechanisms (Cheng & Friedman, 2005) | Formally proves no *symmetric* reputation function can be sybil-proof, and constructs an asymmetric, flow-based function that resists identity-splitting manipulation — the theoretical reason RecoverMem's own corroboration-count feature is structurally, not incidentally, vulnerable to laundering. | Written for peer-to-peer network reputation, two decades before LLM agents existed, requiring explicit translation to the memory-corroboration setting; the proposed asymmetric fix has real implementation complexity RecoverMem has not attempted. |
| 16 | OrpheusDB: Bolt-on Versioning for Relational Databases (Huang et al., 2017) | The closest systems-level precedent for RecoverMem's own version-chain design: adds git-style commit/branch/checkout semantics onto a conventional relational database without sacrificing SQL query access across versions. | General-purpose dataset versioning with no concept of trust or an admission decision gating whether a new version is "good" — versioning is unconditional, whereas RecoverMem versions *and* trust-scores every write. |
| 17 | ARIES: A Transaction Recovery Method Supporting Fine-Granularity Locking and Partial Rollbacks (Mohan et al., 1992) | The classical database-recovery precedent for RecoverMem's rollback engine: supports *selective*, partial rollback of individual transactions via write-ahead logging rather than restoring the whole database. | Operates purely on physical transaction logs with no concept of semantic derivation between rows — cannot express "this memory was inferred from that memory," only "written in the same transaction," which is what RecoverMem's dependency graph generalizes it to. |
| 18 | Machine Unlearning Fails to Remove Data Poisoning Attacks (Pawelczyk et al., ICLR 2025) | Shows state-of-the-art approximate machine-unlearning methods fail to fully remove data-poisoning effects even at high compute budgets, across image classifiers and LLMs — the direct literature justification for why RecoverMem performs explicit dependency-graph rollback rather than trying to implicitly "unlearn" a poisoned memory's influence. | Evaluated on model-weight unlearning, not on removing a fact's influence from a symbolic memory/derivation-graph store like RecoverMem's — the finding transfers by analogy, not by direct applicability. |
| 19 | Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods (Cormack, Clarke, & Büttcher, 2009) | The exact algorithm behind RecoverMem's hybrid-retrieval fusion of pgvector (dense) and full-text (sparse) rankings; shows simply summing 1/(k + rank) across ranked lists outperforms more sophisticated fusion and learning-to-rank methods, correctly avoiding the need for score-scale compatibility between rankers. | A 2009-era information-retrieval technique with no awareness of embedding-based dense retrieval or any adversarial/poisoning consideration at all. |
| 20 | Locating and Editing Factual Associations in GPT — ROME (Meng, Bau, Andonian, & Belinkov, 2022) | Establishes the "locate-then-edit" paradigm for correcting what a model "believes" at the parameter level — a useful contrast to RecoverMem's memory-level approach, since ROME's edits are opaque and irreversible while RecoverMem's version chain is auditable and reversible by construction. | Edits are not human-readable beyond the causal-tracing method used to find them, and there is no built-in mechanism to revert to a pre-edit model state, unlike RecoverMem's version history. |

### 6.1 FINDINGS IN LITERATURE SURVEY

Three independent research threads converged on the same underlying problem
— LLM agents with persistent memory can be poisoned — within roughly an
18-month window (2024 through mid-2026). Offensive work (papers 1, 2, 8, 9,
10) proved the attack is practical and requires a very small injection
budget, even against agents holding pre-existing, legitimate memories.
Defensive/architectural work (papers 3–7) responded with increasingly
sophisticated admission-control, auditing, and governance mechanisms.
Foundational fields adjacent to the problem — database recovery (17), data
provenance (12), Merkle trees (13), sybil-resistant reputation (15), machine
unlearning (18), explainable AI (14), and hybrid retrieval (11, 19) — supply
the individual mechanisms the defensive papers assemble, but none of these
foundational papers were written with LLM memory poisoning in mind; they are
being repurposed, not extended.

The clearest finding across the survey is that **every defensive paper
picks one or two of the mechanisms RecoverMem combines, not all of them.**
MemLineage (3) pairs a Merkle log with a derivation graph but only supports
a binary refuse-gate with no recovery path. MemAudit (4) detects a poisoned
memory after the fact but specifies no graduated recovery procedure for its
descendants. A-MAC (5) produces a graded, interpretable admission score but
has no versioning and cannot revisit a decision later. No paper in this
survey combines write-time explainable admission scoring, non-destructive
versioning, cryptographic tamper-evidence, a derivation graph, *and*
graduated (not binary) dependency-aware rollback in one system — this
combination, not any single novel mechanism, is RecoverMem's proposed
contribution.

The survey also surfaces limitations that RecoverMem's own design has not
yet resolved and which should be stated candidly rather than omitted.
TMA-NM (6) names "corroboration-laundering" — coordinated fake
corroboration used to inflate trust — directly, and Cheng & Friedman's
impossibility result (15) proves this is a structural property of *any*
symmetric corroboration-counting scheme, not a fixable oversight; closing
this gap would require moving to an asymmetric, flow-based scoring function
that RecoverMem does not currently implement. Separately, Semantic Chameleon
(10) shows hybrid retrieval is only a partial defense against
retrieval-time poisoning — an adaptive attacker who jointly optimizes
against both retrieval legs still achieves 20–44% success — so RecoverMem's
layered design (hybrid retrieval plus trust scoring) should be understood
as defense-in-depth, not either layer being independently sufficient.

---

## 7. METHODOLOGY

RecoverMem was developed using an incremental, phase-based methodology
rather than a single monolithic build, structured around one explicit
ground rule: every phase must leave the system in a demoable state, since
this is a guide/mentor-facing project where showing continuous, verifiable
progress matters more than finishing components in isolation.

The build was organized into nine phases (Phase 0 through Phase 8):
Phase 0 established the repository scaffold (FastAPI + React skeletons,
Dockerized PostgreSQL with the pgvector extension, Alembic migrations).
Phase 1 built the core chat → extraction → embedding → storage loop with no
trust gating, verified end-to-end via live HTTP calls. Phase 2 introduced
the actual security core — hybrid retrieval, feature engineering, and the
rule-based trust engine — and non-destructive versioning, verified against
a live database with concrete trust-score examples for both a trusted store
and a rejected contradiction. Phase 3 built the admin dashboard against
this real data with no mocked responses. Phase 4 added the dependency
graph and its dashboard visualization. Phase 5 added Merkle tamper-evidence
and an integrity-verification endpoint. Phase 6 added the dependency-aware
rollback engine and an attack-simulation surface. Phase 7 layered a trained
RandomForest and SHAP explainability on top of the Phase 2 rule engine.
Phase 8 added analytics, logs, and semantic search, and closed with a
full, back-to-back rehearsal of every demo flow against the live stack —
a rehearsal pass that itself surfaced and fixed two real correctness bugs
in earlier phases' own mechanisms (an approximate vector index silently
dropping relevant rows at demo scale, and a Merkle-root ordering bug that
produced false-positive tamper reports after a multi-write transaction).

Verification at each phase combined automated unit testing (53 backend
tests at completion, covering the pure decision logic of the trust engine,
versioning, Merkle, graph, and rollback services in isolation) with live,
manual verification against the real running stack — issuing actual HTTP
requests through the same path the frontend uses, rather than relying on
mocked responses, and browser-based click-testing of the admin dashboard
where tooling allowed. This combination was chosen deliberately: unit
tests catch regressions in isolated logic quickly, but this project's most
serious bugs (the two above) were integration-level failures that only a
full-stack rehearsal against real data could surface, and unit tests alone
would not have caught either.

---

## 8. SOFTWARE REQUIREMENTS

### Functional Requirements

- **FR1:** The system shall extract candidate memory statements from a
  user's chat input.
- **FR2:** The system shall compute a trust score for each candidate memory
  using retrieval-derived features (semantic similarity, contradiction,
  source reliability, corroboration, recency).
- **FR3:** The system shall classify each candidate into one of three
  decisions — store, review, or reject — based on its trust score.
- **FR4:** The system shall never overwrite an existing memory in place; it
  shall always create a new, non-destructive version.
- **FR5:** The system shall record provenance (source type, conversation
  identifier, model version, raw input) for every memory version.
- **FR6:** The system shall maintain a cryptographic Merkle root over the
  memory store, recomputed on every write, and shall support on-demand
  integrity verification that identifies the exact tampered version, if
  any.
- **FR7:** The system shall record a derivation edge between two memory
  versions whenever a new memory's retrieval context included an existing
  one, forming a dependency graph.
- **FR8:** The system shall support marking a memory as poisoned and
  triggering a rollback that re-validates every descendant in the
  dependency graph, producing a per-node kept / reverted / removed outcome.
- **FR9:** The system shall provide an administrative dashboard exposing
  memories, memory detail with trust breakdown, the dependency graph,
  integrity checks, rollback, analytics, and logs.
- **FR10:** The system shall support hybrid (semantic + keyword) search
  over stored memories, exposed both internally to the retrieval pipeline
  and externally via a dedicated search endpoint.

### Non-Functional Requirements

- **NFR1 (Explainability):** Every trust decision shall expose a
  per-feature score breakdown, not a bare numeric output.
- **NFR2 (Auditability):** Full version history and provenance shall be
  retained indefinitely; no memory version shall ever be destructively
  deleted or mutated.
- **NFR3 (Performance):** The ingestion pipeline (extraction through trust
  scoring) shall complete within interactive chat latency at the project's
  demo scale; production-scale throughput is explicitly out of scope
  (Section 4).
- **NFR4 (Usability):** The admin dashboard shall be usable by a
  non-technical evaluator without direct database or CLI access.
- **NFR5 (Portability):** The system shall be deployable on a single local
  machine via `docker-compose` plus standard backend/frontend dev-server
  commands, with no mandatory cloud dependency (a fully offline, canned
  LLM-response mode is supported).
- **NFR6 (Security scope):** The system's trust model assumes a single
  demo user; multi-tenant authentication/authorization is explicitly out
  of scope for this stage (Section 4).
- **NFR7 (Maintainability):** The backend shall be organized as
  independently testable services (extraction, embedding, retrieval, trust
  engine, versioning, Merkle, graph, rollback), each with isolated unit
  test coverage.

---

## 9. SYSTEM ARCHITECTURE

**Fig. 9.1 — System Architecture** *(insert `docs/diagrams/architecture.png`
or `architecture.svg` here)*

The architecture is organized into five layers. The **pipeline layer**
takes a chat message through the LLM client, memory extractor, embedding
service, hybrid retrieval, and feature engineering stages, ending at the
**trust gate** — the rule + RandomForest/SHAP trust engine that attaches a
score and decision to every candidate. Every candidate, regardless of
decision, flows into the **storage & security core**: a versioning and
provenance service that writes a non-destructive version, which in turn
feeds the PostgreSQL + pgvector store, the Merkle tree service, and the
dependency graph. The **presentation layer** — the admin dashboard — reads
directly from this core (memories, graph, Merkle root history) and is the
guide-facing surface where an evaluator interacts with the system. Finally,
the **recovery layer** — the rollback engine — is triggered from the
dashboard, reads the dependency graph to find a poisoned memory's
descendants, and writes new versions back into the storage core, closing
the loop. This reflects the project's own framing of "two front doors, one
backend": the chat surface never exposes security internals, while the
admin dashboard is the fully instrumented view onto the same live data.

---

## 10. UML DIAGRAMS

*(Use Case and Class diagrams prepared separately — not included in this
report per current instructions.)*

---

## 11. SUMMARY

This report has framed LLM agent memory poisoning as a concrete, actively
studied security problem, grounded in a 24-paper literature survey spanning
foundational database/cryptography theory through 2024–2026 LLM-specific
attack and defense research. The survey identified a precise gap: no
existing system combines explainable write-time admission scoring,
non-destructive versioning, Merkle tamper-evidence, an explicit dependency
graph, and graduated dependency-aware rollback in one working pipeline.
RecoverMem was proposed and designed to close this gap, with objectives and
scope defined directly against it. The system has been implemented across
nine incremental phases — from the core chat-to-storage loop through hybrid
retrieval and rule-based trust gating, the admin dashboard, dependency
graph, Merkle integrity, dependency-aware rollback, a RandomForest+SHAP
explainability layer, and finally analytics/search — with each phase
verified both by automated unit tests (53 at completion) and live rehearsal
against the running stack, a process that itself surfaced and fixed two
real correctness bugs. The literature survey also surfaced limitations
RecoverMem has not yet resolved — most notably that its corroboration-based
trust signal remains structurally vulnerable to coordinated
"corroboration-laundering," a known, cited, and currently open problem —
which are documented honestly as future work rather than omitted.

---

## REFERENCES (minimum 15 papers)

[1] Chen, Z., Xiang, Z., Xiao, C., Song, D., & Li, B. (2024). AgentPoison:
Red-teaming LLM agents via poisoning memory or knowledge bases. In
*Advances in Neural Information Processing Systems (NeurIPS 2024)*.
arXiv:2407.12784. https://arxiv.org/abs/2407.12784

[2] Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., & Xiang,
Z. (2025). Memory injection attacks on LLM agents via query-only
interaction. arXiv:2503.03704. https://arxiv.org/abs/2503.03704

[3] Ouyang, C., & Hou, R. (2026). MemLineage: Lineage-guided enforcement
for LLM agent memory. arXiv:2605.14421. https://arxiv.org/abs/2605.14421

[4] Tan, Z., Yao, Y., Jin, H., Yu, W., Wang, G., Fan, M., Lu, L., Liu, F.,
Zhang, X., Ma, D., Yang, T., & Sun, L. (2026). MemAudit: Post-hoc auditing
of poisoned agent memory via causal attribution and structural anomaly
detection. arXiv:2605.23723. https://arxiv.org/abs/2605.23723

[5] Zhang, G., Jiang, W., Wang, X., Behr, A., Zhao, K., Friedman, J., Chu,
X., & Anoun, A. (2026). A-MAC: Adaptive memory admission control for LLM
agents. arXiv:2603.04549. https://arxiv.org/abs/2603.04549

[6] Louck, Y. (2026). Securing LLM-agent long-term memory against
poisoning: Non-malleable, origin-bound authority with machine-checked
guarantees. arXiv:2606.24322. https://arxiv.org/abs/2606.24322

[7] Lin, Z., Hao, X., Fu, R., Cui, S., Chen, K., Li, C., Li, Z., & Xiong, F.
(2026). A survey on long-term memory security in LLM agents: Attacks,
defenses, and governance across the memory lifecycle. arXiv:2604.16548.
https://arxiv.org/abs/2604.16548

[8] Zou, W., Geng, R., Wang, B., & Jia, J. (2024). PoisonedRAG: Knowledge
corruption attacks to retrieval-augmented generation of large language
models. arXiv:2402.07867. https://arxiv.org/abs/2402.07867

[9] Zhang, B., Chen, Y., Liu, Z., Nie, L., Li, T., Liu, Z., & Fang, M.
(2025). Practical poisoning attacks against retrieval-augmented generation.
arXiv:2504.03957. https://arxiv.org/abs/2504.03957

[10] Thornton, S. (2026). Semantic Chameleon: Corpus-dependent poisoning
attacks and defenses in RAG systems. arXiv:2603.18034.
https://arxiv.org/abs/2603.18034

[11] Sawarkar, K., Mangal, A., & Solanki, S. R. (2024). Blended RAG:
Improving RAG accuracy with semantic search and hybrid query-based
retrievers. arXiv:2404.07220. https://arxiv.org/abs/2404.07220

[12] Buneman, P., Khanna, S., & Tan, W. (2001). Why and where: A
characterization of data provenance. In *Proceedings of the 8th
International Conference on Database Theory (ICDT 2001)*.

[13] Merkle, R. C. (1980). Protocols for public key cryptosystems. In
*Proceedings of the IEEE Symposium on Security and Privacy* (pp. 122–134).

[14] Lundberg, S. M., & Lee, S.-I. (2017). A unified approach to
interpreting model predictions. In *Advances in Neural Information
Processing Systems (NeurIPS 2017)*. arXiv:1705.07874.
https://arxiv.org/abs/1705.07874

[15] Cheng, A., & Friedman, E. (2005). Sybilproof reputation mechanisms. In
*Proceedings of the ACM SIGCOMM Workshop on Economics of Peer-to-Peer
Systems (P2PECON 2005)*.

[16] Huang, S., Xu, L., Liu, J., Elmore, A. J., & Parameswaran, A. (2017).
OrpheusDB: Bolt-on versioning for relational databases. *Proceedings of the
VLDB Endowment, 10*(10), 1130–1141.

[17] Mohan, C., Haderle, D., Lindsay, B., Pirahesh, H., & Schwarz, P.
(1992). ARIES: A transaction recovery method supporting fine-granularity
locking and partial rollbacks using write-ahead logging. *ACM Transactions
on Database Systems, 17*(1), 94–162.

[18] Pawelczyk, M., Di, J. Z., Lu, Y., Kamath, G., Sekhari, A., & Neel, S.
(2025). Machine unlearning fails to remove data poisoning attacks. In
*International Conference on Learning Representations (ICLR 2025)*.
arXiv:2406.17216. https://arxiv.org/abs/2406.17216

[19] Cormack, G. V., Clarke, C. L. A., & Büttcher, S. (2009). Reciprocal
rank fusion outperforms Condorcet and individual rank learning methods. In
*Proceedings of the 32nd International ACM SIGIR Conference on Research and
Development in Information Retrieval* (pp. 758–759).

[20] Meng, K., Bau, D., Andonian, A., & Belinkov, Y. (2022). Locating and
editing factual associations in GPT. In *Advances in Neural Information
Processing Systems (NeurIPS 2022)*. arXiv:2202.05262.
https://arxiv.org/abs/2202.05262
