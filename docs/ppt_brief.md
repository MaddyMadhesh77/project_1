# RecoverMem — PPT Generation Brief

Paste the block below into whatever AI slide tool you're using (Gamma,
Copilot, Canva Magic Design, ChatGPT, etc.) as the context/prompt. It's
self-contained — every fact in it is pulled from this repo's own docs
(DESIGN.md, PLAN.md, literature_review.md, literature_survey_findings.md,
bugs.md), so the AI isn't inventing content, just formatting it.

---

## Master prompt to paste

```
Create a 20-slide academic project review presentation for "RecoverMem," a
security middleware between an LLM agent and its long-term memory store. It
trust-scores candidate memories before persisting, versions instead of
overwriting, tamper-evidences the store with a Merkle tree, and tracks
derivation dependencies so a poisoned memory and everything derived from it
can be found and rolled back. Audience: a university/capstone project review
panel (mentor/evaluator "Guide"). Tone: technical, precise, confident but
honest about limitations — this is a working MVP, not vaporware, and the
presenter wants to show critical self-analysis, not just a feature list.
Keep bullets short (max ~6 words each where possible); one core idea per
slide; use the exact numbers given, don't round or embellish them.

Use exactly these 20 slides, in this order, with this content:
```

Then paste the slide-by-slide content below it (or feed it in one shot — most
tools handle a single long prompt fine).

---

## Slide-by-slide content

**1. Title Slide**
- RecoverMem — Security Middleware for LLM Agent Memory
- Subtitle: Trust-gated · Versioned · Tamper-evident · Dependency-aware
- [Your name / guide name / institution / date]

**2. Problem Statement & Motivation**
- LLM agents with persistent memory can be poisoned: one false statement, once stored, is treated as ground truth forever
- Mainstream memory pipelines (Mem0-style extract → dedupe → store) have no concept of trust, provenance, or blast radius
- Can't answer: should this be believed? where did it come from? what breaks if it's false?
- RecoverMem = middleware that intercepts every write before persistence

**3. Literature Review — Overview & Timeline**
- 24 independently-verified papers, 2001–2026, across 12 themes
- Arc: 1980 Merkle trees → 2001 provenance theory → 1992 ARIES recovery → 2005 Sybilproof reputation → 2009 reciprocal rank fusion → 2012 first ML poisoning attack → 2017 SHAP / git-style DB versioning → 2022 model editing (ROME) → 2023 prompt injection → 2024 AgentPoison/PoisonedRAG → 2025–26 MemLineage/MemAudit/A-MAC/TMA-NM
- Shows "trust the input" is the oldest known ML-security failure mode, now recurring at the agent-memory layer

**4. Literature Review — Key Papers**
- MemLineage (2026) — Merkle+DAG, binary refuse-gate
- MemAudit (2026) — post-hoc causal-attribution auditing
- A-MAC (2026) — interpretable 5-factor admission scoring
- TMA-NM (2026) — formally verified non-malleable authority
- PoisonedRAG / AgentPoison (2024) — proved memory poisoning is practical
- SHAP (2017) — the explainability method RecoverMem's trust engine uses
- Machine Unlearning Fails to Remove Poisoning (ICLR 2025) — why implicit "unlearning" doesn't work

**5. Related Work — Positioning Table**
- Table: MemLineage / MemAudit / A-MAC / TMA-NM / Survey vs. RecoverMem
- Columns: graded vs binary gate, versioning, tamper-evidence, dependency graph, rollback granularity, corroboration-attack awareness
- RecoverMem is the only row with every column checked except the last one — disclosed honestly, not hidden

**6. Gap Identification**
- No prior system combines write-time explainable admission + non-destructive versioning + Merkle tamper-evidence + dependency graph + graduated rollback
- MemLineage: binary refuse only, no recovery
- MemAudit: detects poison, no recovery procedure
- A-MAC: scores admission, no versioning or recheck
- Machine unlearning (ICLR 2025): proven not to fully remove poisoning effects — this is why RecoverMem uses explicit graph rollback instead

**7. Objectives**
- Gate every write through an explainable trust decision (store/review/reject)
- Never destructively overwrite — full Git-style version history
- Full provenance per memory version (who/what/when/source/model)
- Tamper-evidence via Merkle tree over the store
- Explicit dependency graph to trace blast radius
- Dependency-aware graduated rollback (keep/revert/remove)
- A demoable admin dashboard, not just a backend

**8. Goals & Non-Goals (Scope)**
- Goals: as above
- Non-goals: multi-tenant auth, production-scale vector search, production-grade ML classifier, arbitrary LLM providers
- Explicit scoping shown as engineering discipline, not gaps

**9. System Architecture**
- Chat UI → FastAPI → Extraction → Embedding → Hybrid Retrieval → Trust Engine → Versioning → Merkle → Dependency Graph
- Admin dashboard reads the same live data, no mocks
- Stack: Python/FastAPI, Postgres+pgvector, React/Vite/TS, sentence-transformers, scikit-learn (RF+SHAP), networkx

**10. Data Model (Entities & Schema)**
- 7 tables: memories, memory_versions, provenance, dependency_edges, merkle_roots, trust_events, rollback_events
- Core rule: versions are append-only, never mutated or deleted

**11. Use Case Diagram**
- [Insert diagram]
- Actors: User, Guide/Admin, Attacker
- Core use cases: chat ingestion, dashboard views, integrity verification, attack simulation, rollback

**12. Class Diagram**
- [Insert diagram]
- 7 entity classes (Memory, MemoryVersion, Provenance, DependencyEdge, MerkleRoot, TrustEvent, RollbackEvent) with relationships/multiplicities

**13. Build Methodology — Phase Roadmap**
- 8 phases (0–8), each ending in a verified, demoable state — "always demoable" as an explicit ground rule
- Phase 0: scaffold → Phase 2: trust gating live → Phase 5: Merkle → Phase 6: rollback → Phase 7: ML layer → Phase 8: analytics + full rehearsal

**14. Trust Engine — Rule-Based Scoring**
- Additive score: source(30) + similarity(24) + novelty(24) + context(18) + contradiction(−40) + corroboration(cap 20)
- Thresholds decide store / review / reject
- Worked example: "I like Python" → 72 → store; later "I hate Python" contradicting it → 34.7 → reject/quarantined

**15. Trust Engine — ML Layer (RandomForest + SHAP)**
- RandomForest trained on 60 hand-authored synthetic examples + real logged outcomes
- Blends 100×P(safe) with the rule score once training data clears a minimum-samples threshold
- shap.TreeExplainer gives real, exact per-feature contributions → the trust_breakdown shown in the dashboard

**16. Versioning, Provenance & Merkle Integrity**
- current_version_id always advances even on reject — required so rollback has something to revert from
- Provenance table: who/what/when/source/model per version
- content_hash = sha256(text + embedding + provenance), recomputed on every write; /integrity/verify names the exact tampered version

**17. Dependency Graph & Rollback Engine**
- dependency_edges written when a new memory's retrieval hit clears a similarity threshold
- Rollback: BFS over descendants, re-evaluate each with the poisoned ancestor's support excluded
- Three outcomes per node: kept / reverted / removed — never mutates a row, always writes a new version

**18. Demo — Attack Simulation Flows**
- 5 flows: poison+reject live, dependency-aware rollback, tamper detection via Merkle mismatch, SHAP explainability panel, semantic search
- (Keep this slide light — signpost for a live demo, not a content dump)

**19. Results, Analysis & Bugs Found**
- 53 backend tests passing; full 5-flow rehearsal against the real stack
- 2 real bugs found and root-caused during rehearsal: pgvector's ivfflat index silently dropping rows at demo scale; merkle_roots timestamp ordering causing false-tamper reports after multi-write transactions
- 43 additional known issues catalogued (concurrency, auth gaps, query efficiency) — proactive self-audit, not defects found by someone else

**20. Limitations, Future Work & Conclusion**
- Corroboration-laundering is unresolved: a false first statement, once repeated, becomes harder to correct than to plant (traced through actual scoring weights)
- Rule-engine weights are uncalibrated relative to field standards
- Hybrid retrieval is a partial defense — an adaptive attacker still achieves 20–44% success
- Future work: asymmetric/sybil-resistant corroboration scoring, weight calibration, authentication layer
- Conclusion: RecoverMem is a coherent, demoable integration of literature-established mechanisms — not a novel primitive, but a working system nothing in the literature assembles end-to-end
```
