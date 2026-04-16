# Claude working notes

## Change workflow: Coder / Reviewer / Implementer

For any non-trivial change (bug fix, feature, refactor), use three roles:

1. **Coder** — designs proposed fixes. Reads the relevant code, writes a concrete proposal (what to change, where, why). Does not edit files.
2. **Reviewer** — reads the Coder's proposal alongside the actual code. Flags risks, edge cases, and impact on other code areas the Coder may not have considered. Does not edit files.
3. **Implementer** — reads both the proposal and the review, makes the final call on what to apply (including rejecting parts of the proposal), applies the edits, and runs tests.

Typical execution: spawn Coder and Reviewer as separate agents (in parallel when their work is independent; sequentially when Reviewer needs the Coder's output). Claude acts as Implementer, or spawns one if the change is large enough to warrant isolation.

Skip this structure only for trivial changes (typo fixes, single-line tweaks, formatting).
