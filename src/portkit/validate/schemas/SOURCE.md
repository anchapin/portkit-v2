# Vendored Bedrock JSON schemas

From the npm package [`@minecraft/bedrock-schemas`](https://www.npmjs.com/package/@minecraft/bedrock-schemas),
built from [Mojang/bedrock-schemas](https://github.com/Mojang/bedrock-schemas) (MIT, see each snapshot's `LICENSE`).
Only `schemas/bp/blocks/` and `schemas/bp/items/` are vendored (the files the validator reads), plus the
`schemas/common/` files they reference that the package ships.

| snapshot dir | package version | upstream commit (`gitHead`) | npm published |
| --- | --- | --- | --- |
| `1.26.60/` | `@minecraft/bedrock-schemas` 1.26.60-beta.24 | `fc31f9af6d2076b16985c12911f52f7e0b3f4251` | 2026-09-30 |

`portkit schemas` reads and rewrites the rows of this table, so keep their format.

Upstream references `../../common/expression.schema.json`, which the package does not publish;
`portkit.validate.schema` treats a missing `$ref` target as "accept anything".

## Refreshing a snapshot (#155)

A snapshot can be vendored from a prerelease (`-beta.N`) while its game version is in Preview.
Once Mojang publishes the stable package for that version, re-vendor it:

1. `portkit schemas check` says, per snapshot, `current`, `waiting` (no stable package yet; names the
   latest stable and newest prerelease) or `REFRESH DUE` (exit code 1). Exit code 2: registry unreadable.
2. `portkit schemas refresh --snapshot 1.26.60 --dry-run` lists the files and block components the stable
   package adds, removes or changes; without `--dry-run` it re-vendors `bp/blocks` and `bp/items` (the
   tarball is checked against the registry's sha512), copies the referenced `common/` files and `LICENSE`,
   and rewrites the row above (version, `gitHead`, publish date). `--version X --allow-prerelease` vendors
   a prerelease instead; `--tarball PATH` uses a downloaded `.tgz`.
3. `python scripts/build_bedrock_reference.py` regenerates the agent's Bedrock reference: its block
   component topics come from `bp/blocks/block_components.schema.json`
   (`tests/test_bedrock_lookup.py` fails until it is rerun when a component is added).
4. For each block component added, removed or renamed, check what the converters emit
   (`portkit.validate.schema.known_block_components` reads the schema, so an emitted component the
   schema drops becomes a `schema.unknown_component` error).
5. Run `pytest -q`, `portkit eval` and `portkit eval --corpus --mct` and confirm no coverage regression
   or new validator errors.

Adding a snapshot for a new format version is different: see the module docstring of
`portkit/validate/schema.py`.
