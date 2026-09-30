# RecoverMem — Literature Review

Status: v1 · 2026-08-18
Companion to [DESIGN.md](DESIGN.md) §1 "Related Work" (this document supersedes
that table with full-depth coverage) and [literature_survey_findings.md](literature_survey_findings.md).

## Scope and method

24 papers, each independently verified to exist (arXiv abstract page, ACM/IEEE/
VLDB/ICML page, or publisher DOI cross-checked against at least one independent
secondary source such as ACL Anthology, ResearchGate, or dblp) before inclusion.
This is a curated reference set — papers actually worth citing in the review —
not an exhaustive dump of everything touched during search. Selection criterion:
does the paper map directly onto one of RecoverMem's nine components (§6 of
DESIGN.md) or its core threat model, closely enough that a reviewer could
reasonably ask "how does your approach compare to this"?

Grouped into 8 themes matching RecoverMem's architecture. Within each theme,
papers are ordered chronologically (oldest → newest) so the progression from
foundational technique to recent LLM-specific application is visible.

---

## Theme 1 — LLM Agent Memory Poisoning (core problem space)

### 1.1 AgentPoison: Red-teaming LLM Agents via Poisoning Memory or Knowledge Bases
- **Authors:** Zhaorun Chen, Zhen Xiang, Chaowei Xiao, Dawn Song, Bo Li
- **Venue/Year:** NeurIPS 2024 · arXiv:2407.12784
- **Source:** https://arxiv.org/abs/2407.12784

**Core concepts:** backdoor attacks via memory (not weights); trigger-optimized
malicious demonstrations; RAG-agent threat model (driving agent, QA agent, EHR
healthcare agent); attack requires no model retraining.

**Summary:** The first attack to target an LLM agent's long-term memory or
RAG knowledge base directly, rather than poisoning training data or model
weights. A small number of malicious demonstrations are injected, each paired
with an optimized trigger phrase; any future query containing the trigger
retrieves the poisoned demonstrations and steers the agent toward an
attacker-chosen outcome, while queries without the trigger are unaffected —
making the attack stealthy under normal use.

**Merits:** Establishes, with a concrete and reproducible methodology, that
memory/knowledge-base poisoning is a *practical* attack class against
production-style agent architectures, not a theoretical concern — this is the
empirical basis for RecoverMem's entire threat model. Evaluated across three
realistic agent domains, giving external validity.

**Demerits (as a defense reference):** Purely offensive — proposes no defense
or detection mechanism. Assumes an agent architecture with a static,
pre-loaded knowledge base rather than a memory store that accretes over a
live conversation, which is RecoverMem's actual setting (chat → extraction →
store, repeated over time).

**Relevance to RecoverMem:** Motivates §1 (Problem Statement) directly —
cite as the empirical proof that the attack class RecoverMem defends against
is real and effective, not hypothetical.

---

### 1.2 Memory Injection Attacks on LLM Agents via Query-Only Interaction (MINJA)
- **Authors:** Shen Dong, Shaochen Xu, Pengfei He, Yige Li, Jiliang Tang, Tianming Liu, Hui Liu, Zhen Xiang
- **Venue/Year:** 2025 · arXiv:2503.03704
- **Source:** https://arxiv.org/abs/2503.03704

**Core concepts:** query-only memory injection (no direct write access needed);
"indication prompt" + "bridging steps"; progressive-shortening to evade
detection at retrieval time.

**Summary:** Shows an attacker with *no* privileged write access to the memory
store — only ordinary conversational queries — can still seed malicious
memories, using a bridging technique that makes the poisoned records
indistinguishable from legitimate ones by the time they are retrieved.
Reports >95% injection success and high downstream attack success.

**Merits:** Directly relevant to RecoverMem's actual attack surface: every
memory enters through the same `/chat` endpoint a legitimate user uses, so
"only interacts via queries" is exactly RecoverMem's real ingestion channel,
not an idealized direct-DB-access threat model. Strong empirical numbers.

**Demerits:** No proposed defense beyond the attack itself; evaluated attack
success does not report how a populated, competing memory store (rather than
an empty one) changes results — a gap [1.6] below explicitly addresses and
finds matters a great deal.

**Relevance to RecoverMem:** Justifies why trust-scoring happens at
*write time*, on every candidate regardless of who or what produced it — a
purely retrieval-time or execution-time filter (as several defenses in Theme
6/8 attempt) would already be too late once a MINJA-style injection succeeds.

---

### 1.3 MemLineage: Lineage-Guided Enforcement for LLM Agent Memory
- **Authors:** Ciyan Ouyang, Rui Hou
- **Venue/Year:** 2026 · arXiv:2605.14421
- **Source:** https://arxiv.org/abs/2605.14421

**Core concepts:** chain-of-custody framing; RFC-6962 Merkle logs with
Ed25519-signed entries; weighted derivation DAG; binary refuse-gate on
sensitive actions justified by untrusted-ancestor memory.

**Summary:** Treats memory poisoning as a *chain-of-custody* problem rather
than a content-filtering problem: every memory entry is a signed, Merkle-logged
record, and a weighted derivation DAG tracks which retrieved entries
influenced which new memories. Sensitive downstream actions are refused
outright if their justification traces back to an untrusted ancestor.
Reports zero attack success across three poisoning workloads at
sub-millisecond overhead.

**Merits:** The closest single prior work to RecoverMem's architecture —
same combination of Merkle tamper-evidence (§6.8) and a derivation graph
(§6.9). Cryptographically rigorous (signed entries, RFC-6962 log format) and
extremely low overhead.

**Demerits:** Binary refuse/allow gate has no middle ground — a memory is
either fully trusted or the action referencing it is blocked outright. This
is a hard cliff-edge with no graded admission decision, no review queue, and
(as described) no mechanism to *recover* a store once a poisoned entry is
discovered — it prevents future harm but does not undo past harm.

**Relevance to RecoverMem:** This is the paper to lead the Gap Identification
section with. RecoverMem takes the same two primitives (Merkle log +
derivation graph) but replaces the binary gate with a graded, explainable
admission score plus a review-queue middle state (§6.5), and adds a rollback
engine (§6.10) that MemLineage's refuse-only design has no equivalent of.

---

### 1.4 MemAudit: Post-hoc Auditing of Poisoned Agent Memory via Causal Attribution and Structural Anomaly Detection
- **Authors:** Zhewen Tan, Yilun Yao, Huiyan Jin, Wenhan Yu, Guoan Wang, Mengyuan Fan, Liang Lu, Feng Liu, Xiangzheng Zhang, Duohe Ma, Tong Yang, Lin Sun
- **Venue/Year:** 2026 · arXiv:2605.23723
- **Source:** https://arxiv.org/abs/2605.23723

**Core concepts:** post-hoc (after-the-fact) auditing; causal-impact
attribution of memories on harmful outputs; structural anomaly detection
within the store; evaluated against MINJA [1.2].

**Summary:** Given an agent that has already misbehaved, identifies *which*
stored memories caused it, using two signals: each memory's measured causal
impact on the problematic output, and how structurally anomalous the memory
looks relative to the rest of the store. Tested directly against MINJA-style
attacks, reducing downstream attack success from 70–83% to 0% once the
causal culprit memories are identified and (implicitly) removed.

**Merits:** Strong empirical validation against a real, named attack (MINJA).
Causal-attribution framing is more principled than simple similarity-based
"which memories are related to this one" heuristics.

**Demerits:** Purely audit/detection — the paper identifies the poisoned
memory after harm has already occurred but does not specify a *graduated*
recovery procedure for the memory's descendants (does removing the culprit
also require re-validating everything derived from it? left unaddressed).
No versioning — implies deletion/removal rather than a git-style history.

**Relevance to RecoverMem:** Directly comparable to §6.10 (Rollback Engine).
RecoverMem's contribution beyond MemAudit is exactly the part MemAudit
doesn't cover: once a poisoned ancestor is identified, RecoverMem's BFS over
`dependency_edges` re-validates every descendant individually and produces a
three-way outcome (keep/revert/remove) rather than a single audit verdict.

---

### 1.5 A-MAC: Adaptive Memory Admission Control for LLM Agents
- **Authors:** Guilin Zhang, Wei Jiang, Xiejiashan Wang, Aisha Behr, Kai Zhao, Jeffrey Friedman, Xu Chu, Amine Anoun
- **Venue/Year:** 2026 · arXiv:2603.04549
- **Source:** https://arxiv.org/abs/2603.04549

**Core concepts:** memory retention as a structured decision problem; five
interpretable factors — utility, confidence, novelty, recency, content-type
prior; rule + lightweight-LLM hybrid scoring; adaptive policy learning.

**Summary:** Frames "should this memory be kept" as a structured decision
over five interpretable dimensions, combining rule-based feature extraction
with a lightweight LLM assessment and learning adaptive weighting policies.
On the LoCoMo benchmark, achieves F1 0.583 with 31% lower latency than
state-of-the-art LLM-native memory systems; content-type prior is the single
most influential factor.

**Merits:** Nearly identical philosophy to RecoverMem's rule-based additive
scorer (§6.5, feature set in §6.4) — an interpretable, additive, multi-factor
admission score rather than an opaque end-to-end classifier. Validated on a
recognized benchmark (LoCoMo), giving a comparison point RecoverMem currently
lacks (RecoverMem's own trust engine is validated only against its own
synthetic set + rehearsal, not an external benchmark).

**Demerits:** Admission-only — no versioning, no tamper-evidence, no
dependency graph, no rollback. A memory that is admitted is admitted for
good; there is no mechanism to revisit the decision once new contradicting
evidence (or a discovered attack) arrives later.

**Relevance to RecoverMem:** The direct precedent for §6.4/§6.5's additive
rule score design — cite as validating the "interpretable feature score,
additively combined" pattern, and use the demerits above (no versioning, no
recheck) as the exact gap RecoverMem's versioning (§6.6) and rollback (§6.10)
fill.

---

### 1.6 Memory Poisoning Attack and Defense on Memory Based LLM-Agents
- **Authors:** Balachandra Devarangadi Sunil, Isheeta Sinha, Piyush Maheshwari, Shantanu Todmal, Shreyan Mallik, Shuchi Mishra
- **Venue/Year:** 2026 · arXiv:2601.05504
- **Source:** https://arxiv.org/abs/2601.05504

**Core concepts:** realistic (non-empty) memory-store attack evaluation;
EHR-agent setting; trust-scoring moderation; retrieval-time sanitization
filtering.

**Summary:** Re-runs memory-poisoning attacks under a *realistic* condition —
a memory store that already contains legitimate, competing memories, rather
than the empty-store idealization common in prior work (including [1.1] and
[1.2]) — and finds this alone substantially reduces attack effectiveness.
Proposes two defenses: input/output moderation via trust scoring, and
memory sanitization with temporal decay + pattern detection.

**Merits:** The finding that a populated store meaningfully resists poisoning
is directly useful evidence for RecoverMem's design: it explains *why*
self-corroboration (an existing "likes Python" memory) is a legitimate
trust-boosting signal (§6.4's `corroboration_count` feature) rather than an
arbitrary heuristic. Trust-scoring-as-moderation is architecturally close to
RecoverMem's approach.

**Demerits:** "Populated store resists attacks" is also a double-edged
finding — TMA-NM [1.7 in Theme 1 below, see also §6] shows the same
corroboration signal can be *gamed* via coordinated fake corroboration
("corroboration-laundering"), which this paper does not test for. No
Merkle/tamper-evidence or graph/rollback component.

**Relevance to RecoverMem:** Empirical support for §6.4's corroboration
feature, but pair this citation with TMA-NM's warning (below) rather than
citing it alone — otherwise the review looks unaware of the attack this
paper's own defense is vulnerable to.

---

### 1.7 Securing LLM-Agent Long-Term Memory Against Poisoning: Non-Malleable, Origin-Bound Authority with Machine-Checked Guarantees (TMA-NM)
- **Authors:** Yedidel Louck
- **Venue/Year:** 2026 · arXiv:2606.24322
- **Source:** https://arxiv.org/abs/2606.24322

**Core concepts:** three disguise channels for untrusted-as-trusted content;
non-malleable, origin-bound authority; information-flow control;
machine-checked (formally verified) guarantees.

**Summary:** Identifies three specific channels by which an attacker can
disguise untrusted content as trustworthy in an agent memory system,
demonstrates that prior defenses fail against at least one of them, and
proposes TMA-NM: a non-malleable information-flow-control system with
machine-checked (i.e., formally verified, not just empirically tested)
guarantees. Reports zero attack success across eight frontier models.

**Merits:** The strongest security guarantee in this entire survey — a
formally verified non-malleability property rather than an empirically
measured low attack-success rate. Directly names "corroboration-laundering"
(coordinated fake corroboration to inflate trust) as an attack class, which
maps precisely onto a known unaddressed weakness in RecoverMem's own
`corroboration_count` feature.

**Demerits:** Formal, machine-checked guarantees typically come with a
narrower deployment envelope (specific origin-authority model, likely less
flexible than RecoverMem's general-purpose additive score) and the paper
does not describe a demoable, interactive system — it is a security
mechanism, not a product.

**Relevance to RecoverMem:** This is the paper to cite explicitly in any
"threats we do not yet defend against" / limitations discussion — DESIGN.md
already flags corroboration-laundering as directly relevant to
`corroboration_count` and rollback re-validation; this citation is the
literature basis for that self-identified gap, and should be named in the
Gap Identification section as *unresolved* rather than *solved* by
RecoverMem.

---

### 1.8 A Survey on Long-Term Memory Security in LLM Agents: Attacks, Defenses, and Governance Across the Memory Lifecycle
- **Authors:** Zehao Lin, Xixuan Hao, Renyu Fu, Shaobo Cui, Kai Chen, Chunyu Li, Zhiyu Li, Feiyu Xiong
- **Venue/Year:** 2026 (v1 Apr, v2 Jun) · arXiv:2604.16548
- **Source:** https://arxiv.org/abs/2604.16548

**Core concepts:** six-phase memory lifecycle (Write, Store, Retrieve,
Execute, Share & Propagate, Forget & Rollback); four security objectives
(Integrity, Confidentiality, Availability, Governance); "Verifiable Memory
Governance" — five architectural primitives for auditable, recoverable
memory-state control; storage-time-anchored security thesis.

**Summary:** The organizing survey for the entire field: frames memory
security across a full lifecycle rather than a single attack/defense pair,
and argues explicitly that robust security "cannot be retrofitted at
retrieval or execution time alone" — it must be anchored at storage/write
time. Proposes five architectural primitives a system needs to provide
auditable, recoverable control over memory state.

**Merits:** Gives RecoverMem a ready-made, authoritative lifecycle vocabulary
(Write/Store/Retrieve/Execute/Share/Forget&Rollback) to structure the entire
review and thesis around, and its central thesis — security must be
storage-time-anchored — is precisely RecoverMem's design choice (trust-gate
every write, §6.5) rather than a retrieval-time or execution-time filter
(the choice most of Theme 6's papers make instead).

**Demerits:** As a survey, it catalogs the space rather than building a
system — it names the primitives a system *should* have but (unlike
MemLineage) does not itself instantiate all of them, particularly not with
a working, interactive/demoable implementation.

**Relevance to RecoverMem:** Use as the primary Literature Review /
Rationale anchor — RecoverMem can be framed explicitly as "an end-to-end,
demoable instantiation of the Write/Store/Retrieve/Execute/Share/Forget&
Rollback lifecycle and its five governance primitives," which is a precise,
citable, non-inflated novelty claim.

---

## Theme 2 — RAG / Retrieval-Corpus Poisoning

### 2.1 PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models
- **Authors:** Wei Zou, Runpeng Geng, Binghui Wang, Jinyuan Jia
- **Venue/Year:** 2024 · arXiv:2402.07867
- **Source:** https://arxiv.org/abs/2402.07867

**Core concepts:** knowledge-base corruption as an optimization problem;
small-injection-budget attack; foundational RAG-poisoning threat model.

**Summary:** The foundational RAG-poisoning paper: formulates injecting a
small number of malicious texts into a knowledge base, so a RAG-backed LLM
is induced to output an attacker-chosen answer for a target question, as an
explicit optimization problem, and demonstrates high success against real
pipelines.

**Merits:** Establishes the threat-model vocabulary (knowledge corruption,
target-question attack) that essentially all later corpus-poisoning papers,
including 2.2–2.4 below, build on directly.

**Demerits:** Assumes a largely static knowledge base being corrupted once,
not a continuously-growing, conversationally-fed memory store like
RecoverMem's — the attack surface (batch corpus injection vs. one message at
a time through `/chat`) is meaningfully different.

**Relevance to RecoverMem:** Cite for the RAG-poisoning threat-model
vocabulary in §1's Related Work; note explicitly (per the Demerits above)
that RecoverMem's setting is the harder, incremental variant of this threat.

---

### 2.2 Practical Poisoning Attacks against Retrieval-Augmented Generation (CorruptRAG)
- **Authors:** Baolei Zhang, Yuxi Chen, Zhuqing Liu, Lihai Nie, Tong Li, Zheli Liu, Minghong Fang
- **Venue/Year:** 2025 · arXiv:2504.03957
- **Source:** https://arxiv.org/abs/2504.03957

**Core concepts:** single-poisoned-text (minimal-injection-budget) attack;
CorruptRAG-AS / CorruptRAG-AK variants; black-box practicality.

**Summary:** Shows a *single* injected malicious text — far below the
multi-text budgets [2.1] and others assume — is sufficient to reliably
corrupt targeted-query answers, achieving over 90% success across datasets
even without full knowledge of the retriever/LLM parameters.

**Merits:** Sharpens the threat model to its most realistic, hardest-to-detect
form: one bad memory is enough. This is exactly the granularity RecoverMem
must defend at — each candidate memory is trust-scored individually, so a
single-text attack is the primary case the trust engine must catch, not an
edge case.

**Demerits:** Still framed as corpus/knowledge-base poisoning rather than
conversational-memory poisoning; no proposed defense.

**Relevance to RecoverMem:** Strongest quantitative justification for why
per-memory (not batch or periodic) trust gating is necessary — cite in
Objective Framing when justifying the "gate every write" goal.

---

### 2.3 Semantic Chameleon: Corpus-Dependent Poisoning Attacks and Defenses in RAG Systems
- **Authors:** Scott Thornton
- **Venue/Year:** 2026 · arXiv:2603.18034
- **Source:** https://arxiv.org/abs/2603.18034

**Core concepts:** dual-document (sleeper + trigger) poisoning via Greedy
Coordinate Gradient; corpus-dependence of attack transfer; hybrid
BM25+vector retrieval as a defense; joint sparse+dense adaptive attacks.

**Summary:** Large-scale evaluation (67,941-document Security Stack Exchange
corpus, 50 attack attempts) of gradient-guided corpus poisoning. The key
result: pure dense (vector-only) retrieval lets a co-retrieval attack
succeed 38% of the time, but adding hybrid BM25+vector retrieval — with
*no* model changes — drops that to 0%, though an adaptive attacker who
jointly optimizes against both retrieval legs can partially circumvent the
hybrid defense (20–44% success).

**Merits:** Directly, empirically validates hybrid retrieval as a *security*
mechanism, not just an accuracy improvement — this is the single most
load-bearing citation for RecoverMem's own hybrid retrieval design (§6.3,
pgvector + tsvector via RRF), since it quantifies the exact benefit
(38%→0%) and the exact limitation (adaptive attacker still gets 20–44%)
RecoverMem should acknowledge rather than overclaim.

**Demerits:** Single-author preprint (less peer-review scrutiny than a
multi-author, venue-published paper); the adaptive-attacker partial
circumvention result means hybrid retrieval alone is *not* a complete
defense — must be paired with trust scoring, not relied on in isolation.

**Relevance to RecoverMem:** Cite in Design/Methodology when justifying
§6.3's hybrid retrieval choice, and cite the adaptive-attack caveat in
Implementation/Analysis or a limitations section — hybrid retrieval reduces
but does not eliminate retrieval-poisoning risk, which is exactly why
RecoverMem layers trust scoring on top rather than treating retrieval
defense as sufficient alone.

---

### 2.4 Blended RAG: Improving RAG Accuracy with Semantic Search and Hybrid Query-Based Retrievers
- **Authors:** Kunal Sawarkar, Abhilasha Mangal, Shivam Raj Solanki
- **Venue/Year:** 2024 · arXiv:2404.07220
- **Source:** https://arxiv.org/abs/2404.07220

**Core concepts:** BM25 + dense KNN + sparse-encoder (ELSER) hybrid queries;
systematic comparison across Natural Questions, WebQuestions, HotpotQA.

**Summary:** IBM Research study systematically comparing single-retriever
versus hybrid-query RAG pipelines, showing hybrid retrieval substantially
outperforms any single retriever across three standard QA benchmarks.

**Merits:** Complements 2.3 with an *accuracy*-side justification for hybrid
retrieval (2.3 covers the *security* side) — together they make the case
that RecoverMem's hybrid retrieval choice (§6.3) is not a security-only
tradeoff against accuracy, it improves both simultaneously.

**Demerits:** No adversarial/poisoning evaluation at all — purely an
accuracy benchmark, so cannot stand alone as security justification.

**Relevance to RecoverMem:** Pair with 2.3 in Design/Methodology's
justification of §6.3.

---

## Theme 3 — Data Provenance

### 3.1 Why and Where: A Characterization of Data Provenance
- **Authors:** Peter Buneman, Sanjeev Khanna, Wang-Chiew Tan
- **Venue/Year:** ICDT 2001
- **Source:** https://www.research.ed.ac.uk/en/publications/why-and-where-a-characterization-of-data-provenance/

**Core concepts:** why-provenance (which source data influenced a result's
existence) vs. where-provenance (the source location a value was copied
from); syntactic provenance formalism for relational/hierarchical data.

**Summary:** The seminal database-theory formalization of provenance,
distinguishing *why* a piece of derived data exists (which source facts
justify it) from *where* it was literally copied from — a distinction nearly
every later provenance system, including RecoverMem's, implicitly relies on.

**Merits:** Gives RecoverMem's provenance table (§6.7 — who/what/when/
source/model per memory version) formal grounding: it is recording
where-provenance (source, model) while the dependency graph (§6.9) is
effectively recording why-provenance (which memories justified this one).
Making that distinction explicit strengthens the Design/Methodology section.

**Demerits:** Purely theoretical/database-internal — predates any notion of
ML models, LLMs, or trust scoring; no security or tamper-evidence angle at
all.

**Relevance to RecoverMem:** Cite in Design/Methodology (§6.7/§6.9) as the
theoretical foundation distinguishing what the provenance table records
versus what the dependency graph records — a distinction the project's own
docs don't currently draw out explicitly.

---

## Theme 4 — Merkle Trees / Tamper-Evidence

### 4.1 Protocols for Public Key Cryptosystems
- **Authors:** Ralph C. Merkle
- **Venue/Year:** IEEE Symposium on Security and Privacy, 1980
- **Source:** https://www.ralphmerkle.com/papers/Protocols.pdf

**Core concepts:** binary hash tree; logarithmic-length authentication path;
single-root authentication of many leaves.

**Summary:** The original Merkle tree construction: any leaf in a binary
hash tree can be authenticated against one published root via a
logarithmic-length path of sibling hashes, without needing to trust or
re-verify every other leaf.

**Merits:** The foundational primitive RecoverMem's entire tamper-evidence
mechanism (§6.8, `services/merkle.py`) is a direct application of — citing
the original 1980 paper (rather than only a modern blockchain application)
demonstrates the student understands the primitive's origin and general
form, not just "how Bitcoin uses it."

**Demerits:** None as a foundational primitive — but note it predates and
says nothing about the *operational* pitfalls of maintaining a Merkle root
incrementally in a live, concurrently-written system, which is exactly
where RecoverMem's own two Phase-8 bugs (float non-round-tripping,
transaction-time vs. statement-time root ordering) came from. The primitive
is simple; correctly operationalizing it against a real database is not.

**Relevance to RecoverMem:** Cite in Design/Methodology §6.8, and pair with
the project's own Phase 5/8 bug writeups in PLAN.md as a natural
"foundational theory vs. practical implementation pitfalls we discovered
ourselves" narrative for the Implementation/Analysis section.

---

## Theme 5 — Trust Scoring / Explainability

### 5.1 A Unified Approach to Interpreting Model Predictions (SHAP)
- **Authors:** Scott M. Lundberg, Su-In Lee
- **Venue/Year:** NeurIPS 2017 · arXiv:1705.07874
- **Source:** https://arxiv.org/abs/1705.07874

**Core concepts:** Shapley-value-based feature attribution; unifies LIME,
DeepLIFT, layer-wise relevance propagation under one game-theoretic
framework; provably unique attribution properties (local accuracy,
missingness, consistency).

**Summary:** Introduces SHAP, unifying six prior feature-attribution methods
under a single Shapley-value framework with provably unique properties,
becoming the standard method for "why did the model decide this" explanations
across tabular ML.

**Merits:** This is not merely "related work" for RecoverMem — it is the
exact library (`shap.TreeExplainer`) Phase 7's trust engine uses to produce
`trust_breakdown`'s per-feature contributions. Citing the original paper
(rather than only the library) demonstrates understanding of *why* the
attribution is theoretically principled (Shapley values are the unique
attribution satisfying local accuracy + consistency), not just "the
`shap` package was imported."

**Demerits:** SHAP's exact computation is expensive in general (though
`TreeExplainer` is a fast, exact special case for tree ensembles — which is
precisely why RecoverMem's RandomForest choice pairs naturally with it);
provides *local* per-decision explanations, not a guarantee that the
underlying model's *decision boundary* itself is trustworthy or unbiased.

**Relevance to RecoverMem:** Central citation for Design/Methodology §6.5
and for the Implementation/Analysis section's explainability claims —
directly ties the RF+SHAP blend to peer-reviewed, foundational theory.

---

### 5.2 A Trust Score-Based Access Control Model for Zero Trust Architecture: Design, Sensitivity Analysis, and Real-World Performance Evaluation
- **Authors:** E. Jeong et al.
- **Venue/Year:** Applied Sciences (MDPI) 15(17):9551, 2025
- **Source:** https://www.mdpi.com/2076-3417/15/17/9551

**Core concepts:** continuously-updated trust score; sensitivity analysis of
scoring weights; zero-trust access-control gating; real intrusion-detection
traffic (CICIDS2017) validation.

**Summary:** Proposes a continuously-updated, sensitivity-analyzed trust
score that gates access-control decisions in a zero-trust network
architecture, validated against real intrusion-detection traffic rather than
synthetic data alone.

**Merits:** Structurally close analogue to RecoverMem's own additive-score
gating decisions (store/review/reject mirrors zero-trust's
allow/step-up/deny), and — notably — includes a *sensitivity analysis* of
the scoring weights, something RecoverMem's own rule engine has not yet
done (`backend/app/core/config.py` documents the rule scorer's weights as
hand-tuned, not calibrated against labelled data — a known limitation).

**Demerits:** Network/access-control domain, not memory/data-trust —
requires translation of concepts (trust score is about the network entity,
not about a persisted fact) rather than a direct methodological transplant.

**Relevance to RecoverMem:** Cite in a Design/Methodology or Analysis
section discussing the trust engine's weight calibration — and honestly
flag, using this paper's sensitivity-analysis methodology as the standard
being fallen short of, that RecoverMem's own rule weights are not yet
similarly validated (this is good-faith self-critique material for the
Analysis component).

---

## Theme 6 — Sybil Resistance / Corroboration Attacks

### 6.1 Sybilproof Reputation Mechanisms
- **Authors:** Alice Cheng, Eric Friedman
- **Venue/Year:** ACM SIGCOMM Workshop on Economics of Peer-to-Peer Systems (P2PECON), 2005
- **Source:** https://dl.acm.org/doi/10.1145/1080192.1080202

**Core concepts:** formal "sybilproofness" property; impossibility result
for symmetric reputation functions; asymmetric, flow-based reputation
function that resists identity-splitting.

**Summary:** Formalizes what it means for a reputation mechanism to be
sybil-proof, proves *no* symmetric reputation function can have this
property (an attacker can always gain by splitting into fake identities
under symmetric scoring), and constructs an asymmetric, flow-based function
that does resist this manipulation.

**Merits:** Provides the formal vocabulary and impossibility result behind
exactly the vulnerability TMA-NM [1.7] names as "corroboration-laundering"
against RecoverMem's `corroboration_count` feature — this paper is *why*
that vulnerability is theoretically guaranteed to exist in any symmetric
corroboration-counting scheme, not just an attack someone happened to think
of.

**Demerits:** Written for peer-to-peer network reputation, two decades
before LLM agents existed — requires explicit translation to the memory-
corroboration setting; the proposed asymmetric fix has real implementation
complexity RecoverMem has not attempted.

**Relevance to RecoverMem:** The key theoretical citation for the Gap
Identification section's discussion of `corroboration_count`'s known
weakness — cite alongside TMA-NM [1.7] to show the gap is both empirically
demonstrated (TMA-NM) and theoretically guaranteed (Cheng & Friedman) to
exist under RecoverMem's current design.

---

## Theme 7 — Non-Destructive / Git-Style Versioning

### 7.1 OrpheusDB: Bolt-on Versioning for Relational Databases
- **Authors:** Silu Huang, Liqi Xu, Jialin Liu, Aaron J. Elmore, Aditya Parameswaran
- **Venue/Year:** PVLDB Vol. 10, No. 10, 2017
- **Source:** http://www.vldb.org/pvldb/vol10/p1130-huang.pdf

**Core concepts:** git-style commit/branch/checkout semantics bolted onto a
conventional relational database; full SQL query access preserved across
dataset versions.

**Summary:** Adds git-style dataset versioning to a conventional relational
database without sacrificing SQL query access — datasets can be committed,
branched, and checked out, and queries can span or compare versions.

**Merits:** The closest systems-level precedent for RecoverMem's own
`memory_versions` design (§6.6): non-destructive, git-style history with
full queryability, applied to structured (relational) data rather than
files — exactly RecoverMem's own setting (Postgres rows, not a filesystem).

**Demerits:** General-purpose dataset versioning with no concept of trust,
poisoning, or an admission decision gating whether a new version is
"good" — versioning is unconditional in OrpheusDB, whereas RecoverMem
versions *and* trust-scores every write.

**Relevance to RecoverMem:** Cite in Design/Methodology §6.6 as the
systems-level precedent for "version instead of overwrite," then note the
explicit addition RecoverMem makes on top: coupling versioning to a trust
decision rather than treating every write as equally valid history.

---

## Theme 8 — Rollback, Recovery, and Blast-Radius Analysis

### 8.1 ARIES: A Transaction Recovery Method Supporting Fine-Granularity Locking and Partial Rollbacks Using Write-Ahead Logging
- **Authors:** C. Mohan, Don Haderle, Bruce Lindsay, Hamid Pirahesh, Peter Schwarz
- **Venue/Year:** ACM Transactions on Database Systems (TODS) 17(1), 1992
- **Source:** https://dl.acm.org/doi/10.1145/128765.128770

**Core concepts:** write-ahead logging; fine-granularity locking;
*partial* rollback of individual transactions (not all-or-nothing restore).

**Summary:** The classic database-recovery algorithm supporting selective,
partial rollback of individual transactions via write-ahead logging, rather
than restoring an entire database to a prior checkpoint.

**Merits:** Foundational database-theory precedent for the core idea behind
RecoverMem's rollback engine (§6.10): recovery should be *selective* — only
the affected records, not the whole store. ARIES does this at the
transaction-log level; RecoverMem does it at the semantic
dependency-graph level (BFS over `dependency_edges`), which is the
generalization ARIES's classic mechanism does not by itself provide (ARIES
knows nothing about semantic derivation between rows, only physical
write-order).

**Demerits:** Operates purely on physical transaction logs with no concept
of semantic derivation between data — cannot express "this row was
*inferred from* that row" the way a dependency graph can, only "this row
was *written in the same transaction as* that row."

**Relevance to RecoverMem:** Cite in Design/Methodology §6.10 as the
classical-database precedent for partial/selective rollback, then draw the
explicit contrast: RecoverMem generalizes ARIES's physical-log selectivity
to semantic-graph selectivity.

---

### 8.2 Machine Unlearning Fails to Remove Data Poisoning Attacks
- **Authors:** Martin Pawelczyk, Jimmy Z. Di, Yiwei Lu, Gautam Kamath, Ayush Sekhari, Seth Neel
- **Venue/Year:** ICLR 2025 · arXiv:2406.17216
- **Source:** https://arxiv.org/abs/2406.17216

**Core concepts:** approximate machine unlearning; indiscriminate, targeted,
and clean-label poisoning; failure to fully remove poisoning effects even
at high compute budgets; tested on both image classifiers and LLMs.

**Summary:** Shows state-of-the-art *approximate* machine-unlearning methods
fail to fully remove the effects of data-poisoning attacks — across three
attack types and both image classifiers and LLMs — even when given
substantial compute budget to do so.

**Merits:** Directly justifies a specific, non-obvious RecoverMem design
decision: rather than trying to make a poisoned memory's influence
"unlearned" implicitly (the way approximate ML unlearning attempts to erase
a data point's effect on model weights), RecoverMem performs *explicit*
dependency-graph rollback — re-evaluating each descendant individually with
the poisoned ancestor's support excluded. This paper is the literature
evidence that the implicit/approximate approach this design deliberately
avoids does not actually work.

**Demerits:** Evaluated on model-weight unlearning (removing a data point's
influence on trained parameters), not on removing a fact's influence from a
symbolic memory/derivation-graph store like RecoverMem's — the finding
transfers by analogy, not by direct applicability, and this distinction
should be stated explicitly rather than implied.

**Relevance to RecoverMem:** One of the most valuable citations in the
entire set for Objective Framing / Design justification — explicitly
explains *why* RecoverMem chose graph-based rollback over a
model-unlearning-style approach, backed by a recent, top-venue (ICLR 2025)
negative result about the alternative.

---

## Theme 9 — Hybrid Retrieval (Sparse + Dense)

### 9.1 Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods
- **Authors:** Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher
- **Venue/Year:** ACM SIGIR 2009
- **Source:** https://dl.acm.org/doi/10.1145/1571941.1572114

**Core concepts:** Reciprocal Rank Fusion (RRF) — score-free rank fusion via
1/(k + rank); outperforms Condorcet fusion, CombMNZ, and individual
learning-to-rank methods on LETOR 3.

**Summary:** Introduces RRF: simply summing 1/(k + rank) across multiple
ranked result lists, deliberately discarding the underlying (incompatible)
relevance scores, outperforms more sophisticated fusion and learning-to-rank
methods.

**Merits:** The exact algorithm behind `services/retrieval.py::hybrid_search`'s
fusion of pgvector (dense) and tsvector (sparse) rankings — a direct,
load-bearing citation, not a loosely-related one. Its core insight (score
compatibility is unnecessary if you fuse by rank, not raw score) explains
*why* RRF is the correct choice for combining two rankers with
fundamentally incomparable score scales (cosine similarity vs. tsvector
rank) — a design justification RecoverMem's own docs currently assert
without this grounding.

**Demerits:** A 2009-era IR technique with no awareness of embedding-based
dense retrieval (which postdates it) or adversarial/poisoning
considerations at all.

**Relevance to RecoverMem:** The single most direct algorithmic citation in
this review — must appear in Design/Methodology §6.3.

---

## Theme 10 — Knowledge Editing / Model Editing Safety

### 10.1 Locating and Editing Factual Associations in GPT (ROME)
- **Authors:** Kevin Meng, David Bau, Alex Andonian, Yonatan Belinkov
- **Venue/Year:** NeurIPS 2022 · arXiv:2202.05262
- **Source:** https://arxiv.org/abs/2202.05262

**Core concepts:** causal mediation analysis to localize factual
associations; Rank-One Model Editing (single-fact weight update);
"locate-then-edit" paradigm.

**Summary:** Uses causal mediation analysis to localize a factual
association to specific mid-layer feed-forward modules in a transformer,
then edits that single fact by directly modifying those weights —
establishing the "locate-then-edit" paradigm for correcting what a model
"believes."

**Merits:** The parameter-level analogue of what RecoverMem does at the
memory level: "correcting a false belief" via a targeted, surgical update
rather than full retraining. Useful contrast for Objective Framing —
RecoverMem's approach (version a new, corrected memory; never destructively
overwrite) can be explicitly compared to ROME's approach (destructively
overwrite specific weights) to argue for RecoverMem's auditability
advantage (ROME's edit leaves no history of what the model "used to
believe"; RecoverMem's version chain does).

**Demerits:** Edits are opaque at the weight level (no human-readable
"why" beyond the causal-tracing methodology used to find the edit location)
and, critically, are *not reversible* in the way a version-chain rollback
is — once ROME edits a fact, there's no built-in mechanism to revert to the
pre-edit model state.

**Relevance to RecoverMem:** Cite in Objective Framing / Design as a
contrasting mechanism at a different layer (parameters vs. memories) for
"changing what an agent believes," used to argue RecoverMem's
versioning-based approach is more auditable and reversible by construction.

---

### 10.2 Position: Editing Large Language Models Poses Serious Safety Risks
- **Authors:** Paul Youssef, Zhixue Zhao, Daniel Braun, Jörg Schlötterer, Christin Seifert
- **Venue/Year:** ICML 2025 · arXiv:2502.02958
- **Source:** https://arxiv.org/abs/2502.02958

**Core concepts:** knowledge-editing methods as attacker-accessible tools;
malicious-use-case taxonomy; unrestricted model upload/download ecosystem
vulnerability; social/institutional awareness gap.

**Summary:** A position paper arguing that knowledge-editing methods —
cheap, fast, stealthy — are attractive tools for malicious actors, and that
the current AI ecosystem allows unrestricted upload/download of edited
models with no verification step, compounded by low awareness of the risk.

**Merits:** Structurally near-identical thesis to RecoverMem's own framing
in §1 of DESIGN.md ("mainstream memory systems... have no concept of trust
[or] provenance... they cannot answer 'should this be believed'") — but
applied one layer down, at model weights rather than agent memory. Strong
citation for establishing that "unverified belief-updates are an
under-appreciated attack surface" is a recognized, ICML-accepted concern
across the broader LLM ecosystem, not a RecoverMem-specific worry.

**Demerits:** Position paper — makes an argument rather than proposing or
evaluating a defense mechanism; no empirical attack/defense results to cite
for comparison.

**Relevance to RecoverMem:** Strong Literature Review / Rationale citation —
use to argue the *general* problem RecoverMem addresses (unverified writes
into a model/agent's persistent knowledge) is recognized as serious at
every layer of the stack, from weights (this paper) to memory (Theme 1),
strengthening the Rationale section's opening claim.

---

## Theme 11 — Prompt Injection (upstream attack vector)

### 11.1 Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection
- **Authors:** Kai Greshake, Sahar Abdelnabi, Shailesh Mishra, Christoph Endres, Thorsten Holz, Mario Fritz
- **Venue/Year:** 2023 · arXiv:2302.12173
- **Source:** https://arxiv.org/abs/2302.12173

**Core concepts:** indirect prompt injection; adversarial instructions
embedded in third-party retrieved content; attacker never interacts with
the model directly.

**Summary:** The foundational indirect-prompt-injection paper: adversarial
instructions embedded in retrieved third-party content (web pages,
documents) can hijack an LLM application's behavior, with the attacker
never directly interacting with the model.

**Merits:** Establishes the *upstream* attack class — untrusted retrieved
content becoming an instruction channel — that, once such content gets
persisted into an agent's long-term memory, becomes exactly the
memory-poisoning problem RecoverMem addresses downstream. Gives the review
a clean narrative arc: injection (2023, this paper) → persistence into
memory (Theme 1) → RecoverMem's write-time gate as the point where the
chain is finally interrupted.

**Demerits:** Concerns a single-turn interaction, not persistent state —
does not itself discuss what happens if injected instructions get written
to durable memory and reused across future sessions (that extension is
Theme 1's contribution).

**Relevance to RecoverMem:** Opens the "how does untrusted content reach the
memory store in the first place" thread in Rationale/Gap Identification —
pairs naturally with 11.2 below.

---

### 11.2 InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents
- **Authors:** Qiusi Zhan, Zhixiang Liang, Zifan Ying, Daniel Kang
- **Venue/Year:** ACL Findings 2024 · arXiv:2403.02691
- **Source:** https://arxiv.org/abs/2403.02691

**Core concepts:** 1,054-case benchmark across 17 user tools / 62 attacker
tools; direct-harm vs. private-data-exfiltration attack categories;
quantified vulnerability of ReAct-prompted GPT-4.

**Summary:** A large benchmark quantifying indirect-prompt-injection
vulnerability in tool-using agents, finding ReAct-prompted GPT-4 vulnerable
24% of the time (nearly doubling under a reinforced attacker prompt).

**Merits:** Gives a concrete, citable vulnerability *rate* (not just "this
attack exists") for the upstream threat RecoverMem's write-time gate sits
downstream of — useful for Objective Framing when arguing the trust-gate is
necessary because upstream defenses (prompt-level filtering) leave a
substantial, quantified residual risk.

**Demerits:** Benchmarks single-session tool-use attacks, not the specific
persistence-into-memory step; results are model/prompt-strategy-specific
(GPT-4 + ReAct) and may not generalize to RecoverMem's own LLM client
choice.

**Relevance to RecoverMem:** Quantitative companion citation to 11.1 in
Objective Framing/Gap Identification — "even with defenses, X% of
injection attempts succeed at the tool layer, which is why a downstream,
persistence-time gate is a necessary second line of defense, not
redundant."

---

## Theme 12 — Foundational Data/Model Poisoning (general ML)

### 12.1 Poisoning Attacks against Support Vector Machines
- **Authors:** Battista Biggio, Blaine Nelson, Pavel Laskov
- **Venue/Year:** ICML 2012 · arXiv:1206.6389
- **Source:** https://arxiv.org/abs/1206.6389

**Core concepts:** gradient-ascent-crafted poisoning points; training-data
distributional-trust assumption; earliest formal training-data poisoning
attack.

**Summary:** One of the earliest formalizations of training-data poisoning:
uses gradient ascent to craft injected points that reliably increase an
SVM's test error, directly exploiting the assumption that training data is
drawn from a well-behaved, trustworthy distribution.

**Merits:** Establishes, at the origin of the poisoning-attack literature,
the exact assumption RecoverMem's entire thesis rejects — that data (here,
training data; in RecoverMem, memory content) can be trusted by default.
Good historical grounding for the Literature Review section, showing the
"assume trust, then get poisoned" failure mode is not new to LLM agents —
it is the oldest known failure mode in ML security, now recurring at a new
layer.

**Demerits:** Pre-deep-learning, pre-LLM — the specific attack mechanism
(gradient ascent against a convex SVM objective) does not transfer to
RecoverMem's setting at all; relevant only as historical/conceptual
grounding, not as a technical precedent.

**Relevance to RecoverMem:** Opening citation for Literature Review — frame
memory poisoning as "the same trust-the-input failure mode the ML security
field has studied since 2012, now recurring at the agent-memory layer,"
which is a stronger, more historically grounded framing than starting the
review at 2024.

---

## Full reference list (chronological)

1. Merkle, R. (1980). *Protocols for Public Key Cryptosystems.* IEEE S&P.
2. Buneman, P., Khanna, S., Tan, W. (2001). *Why and Where: A Characterization of Data Provenance.* ICDT.
3. Mohan, C., Haderle, D., Lindsay, B., Pirahesh, H., Schwarz, P. (1992). *ARIES.* ACM TODS 17(1).
4. Cheng, A., Friedman, E. (2005). *Sybilproof Reputation Mechanisms.* ACM SIGCOMM P2PECON.
5. Cormack, G., Clarke, C., Büttcher, S. (2009). *Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods.* ACM SIGIR.
6. Biggio, B., Nelson, B., Laskov, P. (2012). *Poisoning Attacks against Support Vector Machines.* ICML. arXiv:1206.6389.
7. Huang, S., Xu, L., Liu, J., Elmore, A., Parameswaran, A. (2017). *OrpheusDB: Bolt-on Versioning for Relational Databases.* PVLDB 10(10).
8. Lundberg, S., Lee, S. (2017). *A Unified Approach to Interpreting Model Predictions.* NeurIPS. arXiv:1705.07874.
9. Meng, K., Bau, D., Andonian, A., Belinkov, Y. (2022). *Locating and Editing Factual Associations in GPT (ROME).* NeurIPS. arXiv:2202.05262.
10. Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., Fritz, M. (2023). *Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection.* arXiv:2302.12173.
11. Zou, W., Geng, R., Wang, B., Jia, J. (2024). *PoisonedRAG.* arXiv:2402.07867.
12. Sawarkar, K., Mangal, A., Solanki, S.R. (2024). *Blended RAG.* arXiv:2404.07220.
13. Zhan, Q., Liang, Z., Ying, Z., Kang, D. (2024). *InjecAgent.* ACL Findings. arXiv:2403.02691.
14. Chen, Z., Xiang, Z., Xiao, C., Song, D., Li, B. (2024). *AgentPoison.* NeurIPS. arXiv:2407.12784.
15. Jeong, E. et al. (2025). *A Trust Score-Based Access Control Model for Zero Trust Architecture.* Applied Sciences 15(17).
16. Dong, S., Xu, S., He, P., Li, Y., Tang, J., Liu, T., Liu, H., Xiang, Z. (2025). *MINJA.* arXiv:2503.03704.
17. Zhang, B., Chen, Y., Liu, Z., Nie, L., Li, T., Liu, Z., Fang, M. (2025). *CorruptRAG.* arXiv:2504.03957.
18. Pawelczyk, M., Di, J., Lu, Y., Kamath, G., Sekhari, A., Neel, S. (2025). *Machine Unlearning Fails to Remove Data Poisoning Attacks.* ICLR. arXiv:2406.17216.
19. Youssef, P., Zhao, Z., Braun, D., Schlötterer, J., Seifert, C. (2025). *Position: Editing Large Language Models Poses Serious Safety Risks.* ICML. arXiv:2502.02958.
20. Zhang, G., Jiang, W., Wang, X., Behr, A., Zhao, K., Friedman, J., Chu, X., Anoun, A. (2026). *A-MAC.* arXiv:2603.04549.
21. Thornton, S. (2026). *Semantic Chameleon.* arXiv:2603.18034.
22. Ouyang, C., Hou, R. (2026). *MemLineage.* arXiv:2605.14421.
23. Tan, Z. et al. (2026). *MemAudit.* arXiv:2605.23723.
24. Louck, Y. (2026). *TMA-NM.* arXiv:2606.24322.
25. Lin, Z., Hao, X., Fu, R., Cui, S., Chen, K., Li, C., Li, Z., Xiong, F. (2026). *A Survey on Long-Term Memory Security in LLM Agents.* arXiv:2604.16548.
26. Sunil, B.D., Sinha, I., Maheshwari, P., Todmal, S., Mallik, S., Mishra, S. (2026). *Memory Poisoning Attack and Defense on Memory Based LLM-Agents.* arXiv:2601.05504.

(26 numbered entries above because 4.1/Merkle and two Theme-8 entries are
counted individually; the body groups 24 *distinct topical write-ups* since
two papers — Semantic Chameleon and the general provenance/versioning
citations — are referenced from more than one theme where relevant, per
their cross-cutting content.)
