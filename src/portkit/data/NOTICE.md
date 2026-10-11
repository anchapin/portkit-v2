# Reference data: sources

Nothing from Mojang/bedrock-samples is stored here or shipped in the package
(#124). The sounds converter and validator read a list of the audio paths named
in Bedrock's vanilla `resource_pack/sounds/sound_definitions.json`, from
[Mojang/bedrock-samples](https://github.com/Mojang/bedrock-samples) at
`46ba6ea985fb5a92d79a9419198f10dda14c199d` (the commit pinned for the agent
reference, see `portkit/agent/reference/NOTICE.md`). That data is (c) Mojang AB,
all rights reserved; use is subject to the
[Minecraft EULA](https://www.minecraft.net/en-us/eula).

`portkit reference fetch` downloads the file at that commit, derives the path
list (paths only: no audio and no definitions), checks it against the sha256
pinned in `portkit/data/__init__.py` and caches it under
`~/.cache/portkit/reference/` (`$XDG_CACHE_HOME`, or `$PORTKIT_REFERENCE_CACHE`
to move it). Without it, vanilla sound references are dropped with a note
saying to run the fetch. `python scripts/build_vanilla_sounds.py` prints the
sha256 to pin after bumping the commit (`--check` says whether the pin is
current).
