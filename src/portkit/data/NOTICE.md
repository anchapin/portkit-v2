# Reference data: sources

`bedrock_vanilla_sounds.txt.gz` is the list of audio paths named in Bedrock's
vanilla `resource_pack/sounds/sound_definitions.json`, from
[Mojang/bedrock-samples](https://github.com/Mojang/bedrock-samples) at
`46ba6ea985fb5a92d79a9419198f10dda14c199d` (the commit pinned for the agent
reference, see `portkit/agent/reference/NOTICE.md`). Paths only: no audio and
no definitions. (c) Mojang AB; use is subject to the
[Minecraft EULA](https://www.minecraft.net/en-us/eula). Regenerate with
`python scripts/build_vanilla_sounds.py` (`--check` says whether it is current).
