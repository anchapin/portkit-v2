# Agent transcripts

Recorded agent runs, replayed in CI with no API key (`tests/test_transcripts.py`).
Each file is JSON Lines, one model completion per line, written by
`RecordingClient` (`portkit.agent.transcript`). Replay checks every request
against the recorded digest, so a change to a prompt, a tool or a validator
message that changes what the model would have seen fails the replay at the
first step that differs.

| transcript | mod | what it pins |
| --- | --- | --- |
| `residue_mod.jsonl` | `fixtures/residue_mod` | the tag recipe is converted and validates; the smithing recipe is declined and stays residue |

`residue_mod.jsonl` was recorded from the scripted client in
`tests/test_residue_agent.py`, not a live model. To replace it with a real run:

```bash
portkit convert fixtures/residue_mod/input /tmp/out --agent \
  --agent-record fixtures/transcripts/residue_mod.jsonl
```

then update the expectations in `tests/test_transcripts.py` if the model chose
differently. When a deliberate change breaks a replay, re-record the same way
and commit the new transcript with the change, so the diff shows in review.
