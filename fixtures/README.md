# Golden fixtures

Each case is `input/` (a Java mod tree) and `expected/` (the Bedrock output the
converters must produce, byte for byte except for manifests). `tests/test_fixtures.py`
walks every case; `portkit eval` prints the coverage table.

Adding a fixture is how you add a regression test. When a conversion is wrong in
the wild, the fix is: shrink it to a fixture, watch it fail, then fix the converter.
`case.toml` records what the case is for and what it is deliberately not covering.
