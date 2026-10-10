# Vendored Bedrock JSON schemas

From [Mojang/bedrock-schemas](https://github.com/Mojang/bedrock-schemas) (MIT, see each snapshot's `LICENSE`).
Only `schemas/bp/blocks/` and `schemas/bp/items/` are vendored: the files the validator reads.

| snapshot dir | package version | upstream commit | committed |
| --- | --- | --- | --- |
| `1.26.60/` | `@minecraft/bedrock-schemas` 1.26.60-beta.24 | `fc31f9af6d2076b16985c12911f52f7e0b3f4251` | 2026-09-30 |

Upstream references `../../common/expression.schema.json` and `../../common/floatrange.schema.json`,
which it does not publish; `portkit.validate.schema` treats a missing `$ref` target as "accept anything".

To add a snapshot, see the module docstring of `portkit/validate/schema.py`.
