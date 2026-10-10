# Real-mod corpus

Real mods from Modrinth, pinned by version id and sha512 in `mods.toml`. The
jars are **downloaded, never committed**: we measure them, we don't
redistribute them.

```bash
portkit corpus fetch        # into ~/.cache/portkit/mods (PORTKIT_CORPUS_CACHE overrides)
portkit corpus list         # what's pinned and whether it's cached
portkit eval --corpus       # coverage per mod against coverage-baseline.json
portkit eval --corpus --fetch --fixture betterend   # one mod, downloading if needed
```

A download whose hash doesn't match the pin is refused. A mod that's re-uploaded
or pulled upstream fails loudly instead of quietly changing the numbers.

`coverage-baseline.json` is the same ratchet as the hand-built fixtures, plus a
per-mod validator `errors` count. A real mod is allowed to be invalid today,
but it can't get worse unnoticed. Bank an improvement with
`portkit eval --corpus --update-baseline`.

CI: `.github/workflows/real-mods.yml` runs nightly and on demand, with the jars
cached on the manifest's hash. `pytest -q` skips the `realmods` test when the
jars aren't cached, so the normal suite stays offline.

| name | mod | version | loader | Minecraft | license | source |
| --- | --- | --- | --- | --- | --- | --- |
| `farmers_delight_neoforge` | Farmer's Delight | 1.21.1-1.3.4 | NeoForge | 1.21.1 | MIT | [vectorwing/FarmersDelight](https://github.com/vectorwing/FarmersDelight) |
| `farmers_delight_fabric` | Farmer's Delight Refabricated | 26.1-3.6.28 | Fabric | 26.1 | MIT | [MehVahdJukaar/FarmersDelightRefabricated](https://github.com/MehVahdJukaar/FarmersDelightRefabricated) |
| `betterend` | BetterEnd | 21.800.2 | Fabric | 1.21.8 | MIT | [quiqueck/BetterEnd](https://github.com/quiqueck/BetterEnd) |

The license column is the mod's declared license on Modrinth. Some mods license
their art separately; that doesn't matter here because nothing is redistributed.

## Adding a mod

1. Pick a version on Modrinth and read `https://api.modrinth.com/v2/version/<id>`.
2. Add a `[[mod]]` entry with the primary file's `url` and `hashes.sha512`, plus the license and source.
3. Run `portkit corpus fetch && portkit eval --corpus --update-baseline` and commit both files.

Mods from v1 failure reports (#26) belong here too: record the report in `notes`.
