# Audit & Failsafe System — design spec

**Status:** concept / design review — no code in this document has been implemented yet.
**Scope:** the whole pipeline (ingest → entity resolution → scoring → dossier → tip generator → API), plus the Personnel Look-Up tool.
**Companion docs:** `h1b_transparency_engine_spec.md` (product spec), `frontend/app/methodology/page.tsx` (the public-facing methodology & limitations page shipped 2026-04).

---

## 1. Why this document exists

This engine's output is accusatory by nature. A dossier page, an anomaly score, or a
pre-filled WH-4 complaint names a real company — and, via Personnel Look-Up, real
individuals — as suspected fraud actors. The failure costs are asymmetric:

- A **false negative** means one bad actor stays unflagged among thousands. The
  enforcement pipeline loses one lead.
- A **false positive** means a legitimate employer is publicly labeled a fraud
  suspect, possibly reported to DOL/USCIS on a government form, possibly indexed
  by search engines forever — and the operator of this tool carries defamation
  exposure for it.

The methodology page we shipped in April addresses *presentation* (score is a lead,
not a verdict; what each flag does NOT prove; freshness indicators). It does not
address *systemic* failure: what happens when the data, the matching, or the
detectors themselves are wrong. That is what this document designs.

The governing principle throughout: **the severity of a claim scales the
verification required to publish it.** Informational flags can fail open;
accusations must fail closed.

---

## 2. Failure-mode taxonomy — what can actually go wrong

Every failure mode below is grounded in the current code, not hypothetical.
File references are to the state of the repo at the time of writing.

### A. Entity resolution — the wrong company (or person) gets blamed

This is the single highest-risk layer, because every downstream flag inherits its
errors, and because cross-source joins (LCA ↔ USCIS Hub ↔ WHD violations ↔ SOS
registries ↔ DOJ press releases) are all keyed on **normalized name strings**, not
stable identifiers.

- **A1 — Name normalization mangles and collides.**
  `normalize_employer_name()` (`backend/h1b_engine/utils/names.py:54-57`) strips
  suffix tokens with `str.replace()` anywhere in the string, not just at the end.
  Concretely: `" CO"` matches inside `" CONSULTANCY"`, so
  `"TATA CONSULTANCY SERVICES"` normalizes to `"TATANSULTANCY"`; `" PA"` matches
  inside `" PACHECO"`. Two effects, both bad: distinct companies collide onto one
  key (`"ACME SYSTEMS"` and `"ACME SOLUTIONS"` both → `"ACME"`), and mangled keys
  silently *fail* to match across sources, so a violator's later filings escape
  the `POST_SANCTION_FILING` detector. Collisions attach one company's violations
  to another; misses hide real ones.

- **A2 — Namesake false positives on people (worst case in the codebase).**
  `OFFICER_PRIOR_VISA_INDICTMENT` (`backend/h1b_engine/score/detectors.py:655-687`)
  matches SOS officer names against DOJ/ICE fraud defendants **by normalized name
  alone** — no state, no date, no company affiliation, no corroborating attribute.
  And the normalizer used is the *company*-name normalizer, so person names get
  legal-suffix tokens stripped out of their surnames first. A company whose
  director shares a name with any indicted person anywhere in the reference list
  receives a CRITICAL 40-point flag. Common South Asian and Chinese surnames —
  heavily represented in this dataset — make collisions a statistical certainty at
  scale, which also gives this failure mode a discriminatory impact profile.

- **A3 — Corporate-structure blindness.** Franchises, subsidiaries, PEOs
  (professional employer organizations), and payroll agents legitimately produce
  many-entities-at-one-address, name-variant, and payroll-under-a-different-EIN
  patterns that mimic shell clusters. `SHARED_ADDRESS_CLUSTER` fires on any
  address with 5+ employer names — which describes every registered-agent office
  (CT Corporation hosts hundreds of thousands of entities), every coworking
  space, and every large office tower. `NO_PAYROLL_FOR_H1B_VOLUME` fires on any
  employer whose approvals exceed 1.5× reported workers — which describes every
  client of a PEO, because the PEO reports the payroll under its own EIN.

### B. Data quality — the inputs are wrong or stale

- **B1 — Wage-unit fallback fabricates poverty wages.** `annualize_wage()`
  (`backend/h1b_engine/utils/wages.py:40-45`) treats an *unrecognized* unit string
  as annual "as spec does." One typo'd unit upstream ("HOURS", "PER HR") turns a
  $45/hour wage into a $45/year salary and triggers `WAGE_FAR_BELOW_SOC_MEDIAN`
  (HIGH, 25 points) with total confidence.

- **B2 — Schema drift between fiscal years.** The spec itself warns that LCA
  column names shift between years. A silent mis-mapping (wage column offset by
  one, status codes renamed) poisons an entire year of data, and nothing in the
  pipeline currently notices — scoring would happily run on garbage.

- **B3 — Vintage mismatch across sources.** `NO_PAYROLL_FOR_H1B_VOLUME` compares
  USCIS approvals for one fiscal year against payroll counts that may be from a
  different year and a different reporting basis (state UI vs QCEW vs 941). The
  flag's evidence doesn't record which vintages were compared.

- **B4 — Stale accusations.** Debarments end (`debarment_end` exists on the
  `Violation` model but detectors don't uniformly respect it), appeals succeed,
  indictments end in acquittal or dismissal, attorneys get reinstated from the
  EOIR discipline list. A reference list ingested once and never re-verified
  converts *past allegation* into *permanent present-tense accusation*.

### C. Detector logic — no channel for the innocent explanation

Almost every detector has a well-known benign explanation that the current code
cannot see:

| Flag | Fires on | Innocent explanation it can't see |
|---|---|---|
| `NAICS_SOC_MISMATCH` (CRITICAL, 40) | gas-station/retail NAICS + computer SOC | a fuel-retail chain hiring software engineers for its logistics platform; stale or holding-company NAICS |
| `SHARED_ADDRESS_CLUSTER` (HIGH, 20) | 5+ employers at one address | registered agents, coworking, office towers |
| `RESIDENTIAL_ADDRESS` (HIGH, 20) | address classified residential | legitimate home-based startups; geocoder error |
| `NO_PAYROLL_FOR_H1B_VOLUME` (CRITICAL, 40) | approvals > 1.5× workers | PEO/payroll-agent EIN split; brand-new companies staffing up |
| `LAYOFF_WITH_CONCURRENT_H1B` (CRITICAL, 40) | LCA within 90 days of a WARN notice | WARN in one division, H-1B in another; LCA is a renewal/amendment for an existing employee, not a new hire |
| `HIGH_DENIAL_RATE` (MEDIUM, 12) | denial rate > 2× SOC average | tiny denominators — 1 denial out of 2 filings |
| `DOL_BENCHING_COMPLAINT_HISTORY` (HIGH, 30) | violation text contains "FAILURE TO PAY" etc. | token match catches many unrelated wage violations |

Two structural problems compound this:

- **C1 — Correlated flags stack.** Scoring is additive
  (`persist_flags()`, `detectors.py:967-989`). One WARN notice can trigger
  `LAYOFF_WITH_CONCURRENT_H1B` + `LAYOFF_SAME_WORKSITE_H1B` + `LAYOFF_SAME_SOC_H1B`
  = 100 points — a maxed-out "risk score" derived from a *single* underlying fact
  that has an innocent explanation.

- **C2 — Thresholds are uncalibrated.** 1.5× payroll ratio, 5-employer address
  cluster, 50%-of-median wage, 300% volume spike, 2× denial rate — none of these
  numbers has been validated against a single known-outcome case. Nobody can
  currently answer "what fraction of employers flagged CRITICAL are actually bad?"

### D. Aggregation & presentation — true data, misleading conclusion

- **D1 — A 0–100 score implies calibration that doesn't exist.** Readers
  inevitably interpret 85/100 as "85% likely fraudulent." It is actually "sum of
  arbitrary per-flag constants, capped."
- **D2 — No score history or provenance.** `persist_flags()` deletes and rewrites
  flags on every run. An employer scored 85 yesterday and 40 today has no
  explanation of what changed — data, code, or thresholds. Nothing records which
  data vintage or code version produced a published score.
- **D3 — LCA ≠ job.** Certified LCAs are routinely filed and never used, filed in
  multiples per position, or filed for renewals/amendments of existing employees.
  Volume- and layoff-based detectors treat every certified LCA as a new hire.
- **D4 — Allegation ≠ finding.** The indictment flag's own description says
  "indictment or settlement." An indictment is an accusation; a settlement often
  disclaims liability. Rendering them identically to *convictions* on a public
  dossier is exactly the "misleading with true facts" failure.

### E. Downstream amplification — the blast radius of a wrong flag

- **E1 — Tip generator.** `tip_text()` (`backend/h1b_engine/investigate/report.py:412`)
  produces pre-filled DOL WH-4 / USCIS tip text. A false flag here doesn't just
  mislead a reader — it manufactures a government complaint. (The April guardrail
  added a warning panel; nothing *blocks* generation on weak evidence.)
- **E2 — Public API strips context.** `/employer/{ein}` returns the raw score.
  Third parties will re-publish it without the methodology page, the caveats, or
  the freshness indicators. The disclaimers do not travel with the number.
- **E3 — Search indexing makes errors permanent.** A dossier crawled once
  survives its own correction.
- **E4 — Exports have no floor.** `export_high_risk()` (`score/engine.py:95`)
  dumps every employer ≥ a caller-chosen score to CSV with no evidence attached —
  a ready-made "list of fraudulent companies" screenshot.

### F. Adversarial abuse — the tool itself as a weapon

- **F1 — Competitor weaponization.** Nothing rate-limits or attributes tip
  generation; a rival can mass-produce official-looking complaints against a
  target.
- **F2 — Data poisoning.** Planned crowdsourced inputs (visadata-style address
  reports, community corrections) are an injection surface: false "residential
  address" reports against a competitor.
- **F3 — Threshold gaming.** Published fixed thresholds (5 employers/address,
  1.5× ratio, 90-day window) tell sophisticated bad actors exactly how to stay
  under them, while naïve legitimate employers keep tripping them. Over time the
  flagged population *inverts* toward false positives.

### G. Personnel Look-Up — a special class

Accusing individuals is categorically riskier than accusing companies. Two extra
failure modes: (1) namesake matching against individuals has all of A2's problems
with even higher harm; (2) if output is ever used in hiring or contracting
decisions, the tool functionally becomes a consumer reporting agency, implicating
FCRA obligations (accuracy, disputes, permissible purpose) that it does not meet.

---

## 3. Design principles for the failsafe layer

1. **Evidence or it doesn't ship.** Every published claim must be mechanically
   traceable to identified source rows with recorded vintages. A flag whose
   evidence can't be re-derived from raw sources is suppressed automatically.
2. **Confidence is part of the datum.** Match quality (EIN-exact vs
   name+address vs name-only) travels with every flag; a flag is only as strong
   as the weakest join in its evidence chain.
3. **Severity scales verification.** LOW/MEDIUM flags may publish automatically
   with evidence. CRITICAL accusatory flags require a second key — human review —
   before they appear anywhere public.
4. **Allegations decay; accusations expire.** Every reference-list-derived flag
   carries a re-verification date and a disposition field (indicted → convicted /
   acquitted / dismissed). Past `debarment_end` or after acquittal, the flag
   auto-downgrades or retires.
5. **Corrections travel as far as the accusation did.** Score changes are
   versioned, disputes annotate the dossier, and API consumers receive
   correction events — not just silent new numbers.
6. **The engine audits itself on the same cadence it accuses others.** Known
   failure detectors (drift monitors, replay checks, calibration benchmarks) run
   on every scoring cycle, and any of them can halt publication.

---

## 4. The failsafe system — architecture

Seven components. Components 1–5 form the **audit tool** (a `backend/h1b_engine/audit/`
package + `scripts/audit.py` CLI, mirroring the existing `score.py`/`graph.py`
pattern). Components 6–7 are product/process changes.

```
            ┌──────────────────────────────────────────────────────┐
            │  scripts/audit.py                                    │
            │                                                      │
 raw files ─┤ 1. ingest-gate    schema/row-count/distribution      │──▶ quarantine
            │                   checks + vintage stamping          │
 DB flags ──┤ 2. replay         re-derive every published flag     │──▶ auto-suppress
            │                   from raw sources                   │
 matches ───┤ 3. collisions     entity-resolution sampling +       │──▶ review queue
            │                   namesake guard verification        │
 benchmark ─┤ 4. calibrate      precision vs known-outcome sets    │──▶ scorecard + CI gate
 runs ──────┤ 5. drift          run-over-run flag-volume and       │──▶ alarm + kill switch
            │                   score-distribution deltas          │
            └──────────────────────────────────────────────────────┘
            6. Publication gates, disputes, and score versioning (product)
            7. Tip/API/export failsafes and abuse resistance (product)
```

### 4.1 Ingestion integrity gate (`audit ingest`)

Runs between download and load; a failed gate quarantines the batch — scoring
never sees it.

- **Schema contract per source per fiscal year.** Expected columns, types, and
  enumerations (e.g., `CASE_STATUS` values) declared in a checked-in manifest.
  Unknown columns warn; missing/renamed critical columns fail. This is the
  defense against B2.
- **Distribution checks.** Row count within ±X% of the prior equivalent release;
  share of unparseable wage units below a ceiling; annualized-wage distribution
  within sane bounds (P1 > $15k, P99 < $2M); share of LCA rows that fail to match
  any employer below a ceiling. A batch where 4% of wages annualize to under
  $10k is a unit-parsing bug, not a fraud wave.
- **Vintage stamping.** Every loaded row gets `source_file`, `source_release`,
  and `loaded_at`. A new `DataVintage` table (one row per source per release)
  becomes the authority that dossiers, flags, and the freshness UI all read from —
  replacing the current informal freshness ping.

### 4.2 Entity-resolution audit (`audit collisions`) + match confidence

- **Match-confidence tiers**, recorded on every cross-source link:
  `EXACT_ID` (EIN / tax_id) > `NAME_ADDR` (normalized name + address/state) >
  `NAME_ONLY`. Every flag stores the *minimum* tier in its evidence chain.
  `NAME_ONLY` can never support a CRITICAL public flag (see 4.6).
- **Namesake guard for person matching.** A person-name match (fraud defendants,
  disciplined attorneys, personnel look-up) requires the name **plus at least one
  corroborating attribute** — same state, same company affiliation, or
  date-plausible role — before it may activate a flag. Name-only person matches
  become internal review-queue candidates, never public flags. Person names get
  their own normalizer; running them through the company-suffix stripper (A2) is
  simply a bug.
- **Collision sampling.** Each audit run samples: (a) normalized-name groups with
  many distinct raw names (collision suspects), and (b) near-miss pairs that
  *almost* matched (miss suspects), and emits them for human spot-review. The
  observed collision rate is itself a published metric — it feeds the calibration
  scorecard.

### 4.3 Evidence contract + replay auditor (`audit replay`)

- **Per-flag evidence schema.** Each flag type declares required evidence fields
  (source row IDs, case numbers, thresholds applied, data vintages compared,
  match-confidence tier). `persist_flags()` rejects a flag whose evidence is
  incomplete — an unfalsifiable flag is a bug by definition.
- **Nightly replay.** For every *published* flag, re-derive it from raw sources.
  A flag that no longer reproduces (source row corrected upstream, debarment
  expired, attorney reinstated, list entry removed) is auto-suppressed and queued
  for review. This is the mechanism that makes B4 (stale accusations)
  self-healing instead of dependent on someone remembering.
- **Disposition tracking for allegations.** Reference tables for indictments and
  discipline gain `disposition` + `verified_as_of` columns. Replay flags any
  allegation-based entry older than N months without re-verification.

### 4.4 Calibration harness (`audit calibrate`) — the core of the audit tool

The answer to "is the score meaningful?" must be empirical:

- **Positive benchmark set:** employers with adjudicated outcomes — USCIS
  debarments, WHD willful-violator findings, DOJ convictions — scored using only
  data from *before* their enforcement date (so the engine is tested on
  prediction, not hindsight).
- **Negative benchmark set:** a stratified sample of presumed-legitimate
  employers (large public companies, universities, hospitals) *plus* — critically
  — known hard negatives: legitimate staffing firms, PEO clients, coworking-based
  startups, i.e., exactly the populations section C says will be over-flagged.
- **Outputs:** per-flag precision/recall, score-band precision (what fraction of
  70+ scores are true positives), and false-positive exemplars. Written to
  `reports/audit/<date>/scorecard.{md,json}`.
- **Two gates:**
  - **CI gate:** any PR touching detectors, thresholds, or normalization must
    not regress benchmark precision — same pattern as any regression suite.
  - **Publication gate:** a flag type whose measured precision is below a floor
    (e.g., 50%) is demoted to internal-only until its detector improves. Per-flag
    precision is published on the methodology page, replacing implied authority
    with measured authority.
- **Shadow-mode burn-in:** every *new* detector runs internal-only for one full
  data cycle, its hits sample-reviewed, before it can appear on a public dossier.

### 4.5 Drift & self-monitoring (`audit drift`) + kill switches

- **Flag-volume monitor:** a detector whose hit count moves >X% between runs is
  alarmed — that's a schema drift, a normalization change, or an upstream format
  break (B2), not a sudden national fraud wave.
- **Score-distribution monitor:** population histogram compared run-over-run.
- **Per-detector kill switch:** a config flag (no deploy required) that disables
  a single detector's *publication* while leaving it computing internally.
  When the address-classifier vendor has a bad day, we switch off
  `RESIDENTIAL_ADDRESS` in one line, not roll back the site.

### 4.6 Publication gates, disputes, and score versioning (product changes)

- **Two-key rule by tier:**
  - *Tier 1 (LOW/MEDIUM):* auto-publish with evidence attached.
  - *Tier 2 (HIGH):* auto-publish, but the dossier must render the flag's
    "innocent explanations" text (from the methodology glossary) inline —
    not a click away.
  - *Tier 3 (CRITICAL accusatory: officer indictment, ghost payroll,
    post-sanction filing, multi-registration):* requires human review sign-off
    before public display; until then visible only in internal/investigation
    mode. Reviews are logged (who, when, what evidence was checked).
- **Score versioning.** Replace delete-and-rewrite with append-only `ScoreRun`
  records: score, flag set, data vintages, code version (git SHA), threshold
  config hash. Dossiers show "scored <date> · data through <vintage> ·
  methodology v<N>" and a change log. This makes every published number
  reconstructible and every change explainable (fixes D2).
- **Dispute & correction loop.** On-dossier dispute path (employer or public);
  an open dispute (a) freezes tip generation for that employer, (b) badges the
  dossier "under review," and (c) sets `noindex` on the page. Resolved disputes
  leave a permanent public correction note. Corrections are pushed to API
  consumers as events (see 4.7) — the correction travels as far as the number did.
- **Uncertainty-honest score display.** Show score *bands* with the calibrated
  precision for the band ("HIGH — in benchmark testing, N% of employers in this
  band had adjudicated violations"), and cap the contribution of *correlated*
  flags (the three `LAYOFF_*` flags share one underlying event and should share
  one capped contribution), fixing C1/D1.

### 4.7 Output-edge failsafes (tips, API, exports)

- **Tip generator:** blocked unless the employer has ≥1 replay-verified flag at
  the required tier; blocked entirely while a dispute is open; requires a
  click-through attestation in which the user confirms they personally reviewed
  each cited evidence item; embeds data vintage + "generated, not verified"
  language *inside* the generated text (so the caveat survives copy-paste); rate
  limited per user/session against F1.
- **API:** score responses always embed `flags[]`, `data_vintage`,
  `methodology_version`, `caveat_url`, and `disputed: bool`. A bare number is
  never returned. Correction/suppression events are exposed as a feed so
  downstream caches can be invalidated.
- **Exports:** `export_high_risk()` gains the same envelope — evidence summary,
  vintage, caveat header row — and refuses to run against a data vintage that
  failed its ingest gate.
- **Community inputs (future):** crowdsourced reports never move a score
  directly; they only enqueue verification tasks, with per-source provenance and
  reputation weighting (F2).
- **Personnel Look-Up:** namesake guard mandatory (4.2); no public individual
  pages — report-mode output only; a purpose-limitation notice (not for
  employment/credit/housing decisions — not an FCRA consumer report) on every
  report.

---

## 5. Bugs found during this analysis — fix regardless of the rest

These are ordinary defects discovered while grounding the taxonomy; they should be
fixed even if the failsafe layer is descoped:

1. **`normalize_employer_name` strips suffix tokens mid-string**
   (`utils/names.py:54-57`) — should strip only at end-of-string, iteratively
   (`"TATA CONSULTANCY SERVICES"` currently → `"TATANSULTANCY"`).
2. **Person names are normalized with the company normalizer** in the officer
   indictment detector (`score/detectors.py:670`) and disciplined-attorney
   matching — surnames containing " PA", " CO", " INC" etc. get mangled.
3. **`annualize_wage` treats unknown units as annual** (`utils/wages.py:40-45`) —
   should return `None`, and wage detectors should *skip* rather than compare
   when annualization failed.
4. **`persist_flags` erases history** (`score/detectors.py:967-989`) — replaced by
   the append-only `ScoreRun` design in 4.6, but at minimum stop destroying the
   only record of what was previously published.
5. **Officer-indictment match has no corroboration requirement**
   (`score/detectors.py:655-687`) — name-only match currently yields a CRITICAL
   public flag; at minimum require a second attribute before the interim
   failsafe work lands.

---

## 6. Rollout priorities

**Phase 1 — before any public launch (blocking):**
- Section 5 bug fixes.
- Score versioning (`ScoreRun`) + vintage stamping (`DataVintage`).
- Evidence contract enforcement in `persist_flags`.
- Namesake guard + match-confidence tiers; Tier-3 human-review gate.
- Ingest gate with schema contracts for the two core sources (LCA, USCIS Hub).
- Dispute path (even a minimal form → queue → dossier badge).
- Tip-generator gating + attestation; API caveat envelope.

**Phase 2 — first quarter of operation:**
- Calibration harness + published per-flag precision; CI regression gate.
- Nightly evidence replay + allegation disposition tracking.
- Drift monitors + per-detector kill switches.
- Correlated-flag capping and score-band display.

**Phase 3 — as the tool grows:**
- Correction event feed for API consumers.
- Community-input verification queue with provenance weighting.
- Shadow-mode burn-in as a standing policy for all new detectors.
- Periodic adversarial red-team review (sampled manual audit of the top-N
  scored employers each quarter; false-positive postmortems feed threshold
  changes through the CI gate).

---

## 7. What this borrows from proven practice

The audit-tool shape here — checked-in reference contracts, cross-engine
consistency sweeps, bounds-not-exact-value regression tests, source freshness
monitoring, and multi-reviewer sign-off for data changes — mirrors the safeguards
already operating in the sibling Cushion project (`scripts/cliff-audit.mjs`,
`scripts/source-monitor/`, seed-sync tests, the benefit-data two-source rule).
Those exist because a benefits calculator that's wrong misleads one applicant.
This engine, when wrong, indicts a bystander — so every one of those patterns
applies here with a human-review key added on top.
