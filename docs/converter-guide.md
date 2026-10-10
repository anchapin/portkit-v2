# Writing a converter

The repo grows by converters. Each one takes a slice of a Java mod that
currently lands in `unhandled.json` and turns it into Bedrock output, shrinking
the residue the agent has to deal with. This guide walks through writing one end
to end. The worked example is small enough to type in, and it runs.

## The contract

A converter is a pure function:

```python
def convert(mod: SourceMod) -> ConversionResult: ...
```

- `mod.root` is the staged mod (it holds `assets/` and `data/`). `mod.namespace`
  is the namespace this pass converts, and `mod.assets` and `mod.data` are
  `root/assets/<ns>` and `root/data/<ns>`. Converters run once per namespace.
- No network, no model, no randomness, no global state. The same mod in gives
  the same bytes out, which is what makes golden fixtures possible.
- Return a `ConversionResult` (`portkit/model.py`) and fill in all four channels:

| channel | how | when |
| --- | --- | --- |
| `files[relpath] = value` | dict/list → JSON, `str` → text, `bytes` → raw | you converted something |
| `result.claim(mod, path)` | records the source as looked at, returns its relpath | **every** file you open, converted or refused |
| `unhandled.append(Unhandled(rel, kind, reason))` | the specific reason you refused | the mapping needs a guess |
| `notes.append("rel: what was lost")` | a stated loss | converted, but Bedrock can't carry a detail |

**Output paths** are relative to a pack root. `pack.write_tree` sends paths that
start with `recipes/`, `entities/`, `functions/`, `loot_tables/`, `blocks/` or
`items/` to the behavior pack, and everything else to the resource pack.

**Claim what you open.** Any staged file nobody claims is reported as `unowned`
residue. Claiming a file and then refusing it is honest. Opening a file and not
claiming it makes it show up twice.

**Refuse precisely.** The reason is what a human or the agent acts on, so name
the specific thing ("tag 'x:y' covers 2 items: a, b"), not a category ("tags
unsupported"). If you aren't sure what Bedrock does, refuse. A converted file
that loads but behaves wrong is the one outcome this project exists to avoid.

## Worked example: splash texts

A Java mod can ship `assets/minecraft/texts/splashes.txt`, one splash per line,
which replaces the title-screen splashes. Bedrock reads `splashes.json` at the
resource pack root: `{"canMerge": bool, "splashes": [...]}`
([Bedrock Wiki](https://wiki.bedrock.dev/text/splashes)). With `canMerge` false,
only the pack's splashes show, which matches Java's replace. Today that file
lands in `unhandled.json` as `unowned`.

### 1. Write a failing fixture first

```
fixtures/splash_mod/
  case.toml
  input/assets/examplemod/lang/en_us.json            {}
  input/assets/minecraft/texts/splashes.txt          (a few lines)
```

`case.toml`:

```toml
name = "splash_mod"
description = "A mod that replaces the title-screen splashes."
namespace = "examplemod"
expect_valid = true
expect_unhandled = 0
```

Run `pytest -q tests/test_fixtures.py -k splash_mod`. It fails, because the
splashes file is `unowned` residue (`expect_unhandled` is 0). That failure is
your target.

### 2. Write the converter

`src/portkit/converters/splashes.py`:

```python
"""Splash texts.

Java: assets/minecraft/texts/splashes.txt, one splash per line, replacing the
vanilla list. Bedrock: splashes.json at the resource pack root; canMerge false
shows only the pack's splashes, which matches Java's replace.
"""
from __future__ import annotations

from ..model import ConversionResult, SourceMod, Unhandled


def convert(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    path = mod.root / "assets" / "minecraft" / "texts" / "splashes.txt"
    if not path.is_file():
        return result
    rel = result.claim(mod, path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        result.unhandled.append(Unhandled(rel, "splashes", "splashes.txt is not UTF-8"))
        return result
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        result.unhandled.append(Unhandled(rel, "splashes", "splashes.txt has no splash lines"))
        return result
    result.files["splashes.json"] = {"canMerge": False, "splashes": lines}
    return result
```

The file lives outside `mod.namespace`, so every namespace pass produces the
same `splashes.json`. `merge_namespaces` keeps identical output silently and
reports only real conflicts.

### 3. Register it

In `src/portkit/converters/__init__.py`, import the module and add
`splashes.convert` to `CONVERTERS`. Registration is all it takes: the
pipeline, `portkit eval` and the fixture harness all pick it up.

### 4. Make it pass, and pin the output

```bash
pytest -q tests/test_fixtures.py -k splash_mod        # now passes (or skips the byte check: no expected/ yet)
portkit convert fixtures/splash_mod/input /tmp/splash
cp -r /tmp/splash fixtures/splash_mod/expected && rm -f fixtures/splash_mod/expected/{unhandled.json,*.mcaddon}
```

An `expected/` tree turns the fixture into a byte-for-byte golden test (manifests
included, since their UUIDs are derived deterministically). Read the produced
files before you commit them. The golden tree is a claim that the output is
right.

### 5. Unit-test the edges

Put the refusals and notes in `tests/test_<converter>.py`: the empty file, the
non-UTF-8 file, and the case you decided not to guess at. Assert on the reason
text, not just the count.

### 6. Validate, ratchet, open the PR

```bash
pytest -q
portkit eval                      # fails if any fixture lost coverage
portkit eval --update-baseline    # bank the new fixture / the improvement
```

Commit the baseline diff with the converter. In the PR, say what now converts,
what you deliberately refused and why, and cite the Bedrock source for every
format claim.

## When the validator should learn something

If your converter emits a file type the validator doesn't check yet, add the
structural rule in `validate/rules.py` (and a cross-reference in `xrefs.py` if
the file names items or blocks). Ground it in Mojang's docs or samples, and add
a test that a broken file fails. That keeps the agent honest too, since it
works against the same oracle.

## Checklist

- [ ] Pure function, registered in `CONVERTERS`.
- [ ] Every file opened is `claim`ed.
- [ ] Refusals name the specific thing; losses are `notes`.
- [ ] A fixture under `fixtures/` with `case.toml` (and `expected/` once stable).
- [ ] Edge-case unit tests asserting on reasons.
- [ ] `pytest -q` and `portkit eval` green; baseline updated in the same PR.
- [ ] Format claims cited (Microsoft Learn, bedrock.dev, Mojang/bedrock-samples).
