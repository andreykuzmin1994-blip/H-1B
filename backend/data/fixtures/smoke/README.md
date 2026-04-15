## Smoke-test fixtures

Tiny synthetic files used by `scripts/smoke_test.sh` to validate the
end-to-end pipeline without needing the full multi-GB raw extracts.

Three fake employers exercise the main detectors:

| Employer             | State | Signal                                               |
|----------------------|-------|------------------------------------------------------|
| Acme Smoke Test LLC  | GA    | WHD H-1B wage violation + WARN layoff mid-H-1B cycle |
| Globex Staffing Corp | CA    | benching violation + secondary-entity placement      |
| Wayne Enterprises Inc| NY    | clean control (wages above prevailing)               |

The BLS OEWS fixture is stored as CSV for reviewability; the smoke script
converts it to a one-sheet `.xlsx` at runtime (`bls_oews` ingester is
Excel-only).

Files here are obvious synthetic data — none of the names, case numbers,
or tax IDs correspond to real entities.
