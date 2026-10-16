"""In-game checks on a Bedrock Dedicated Server (#238).

``testpack`` writes a check behavior pack for a converted tree; ``server``
fetches the pinned server (only with the EULA accepted), installs the packs,
runs the checks headlessly and reads the result; ``nbt`` toggles a world's
experiments. The CLI is ``portkit ingame``; the workflow is
``.github/workflows/ingame.yml``.
"""
