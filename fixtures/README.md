# Golden fixtures

Each case is `input/` (a Java mod tree) and `expected/` (the Bedrock output the
converters must produce, byte for byte except for manifests). `tests/test_fixtures.py`
walks every case; `portkit eval` prints the coverage table.

Adding a fixture is how you add a regression test. When a conversion is wrong in
the wild, the fix is: shrink it to a fixture, watch it fail, then fix the converter.
`case.toml` records what the case is for and what it is deliberately not covering.

## Coverage baseline

`coverage-baseline.json` records, per fixture, the coverage and the number of
converted files. `portkit eval` (and CI) fails when any fixture drops either one,
naming the fixture and the delta, so coverage only ratchets one way. When a change
improves a fixture, or you add one, run `portkit eval --update-baseline` and commit
the new baseline with the change. A deliberate step down goes through the same
command and shows up as a baseline diff in review.
