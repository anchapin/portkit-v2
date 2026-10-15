"""Keep the vendored Bedrock schemas in step with Mojang's npm releases (#155).

The validator's schemas (``schemas/<snapshot>/``) are copied from the npm
package ``@minecraft/bedrock-schemas`` (MIT, built from github.com/Mojang/
bedrock-schemas). A snapshot may be vendored from a prerelease (``-beta.N``)
while the game's matching version is still in Preview; once Mojang publishes
the stable package for that version, the snapshot should be re-vendored from
it. ``schemas/SOURCE.md`` records which package version each snapshot holds.

``portkit schemas check`` reads that table and the registry's package document
and says, per snapshot, whether a refresh is due:

- ``current``: the snapshot already holds the stable package for its version;
- ``refresh``: it holds a prerelease and the stable package is out (exit 1);
- ``waiting``: no stable package for its version yet (the latest stable and the
  newest prerelease are named).

A stable release *newer* than a snapshot is reported too: that is a new
snapshot to add, not a refresh of this one.

``portkit schemas refresh`` re-vendors a snapshot from a package version: it
downloads the tarball named in the registry document, checks its ``sha512``
integrity, replaces ``bp/blocks`` and ``bp/items`` with the package's
``schemas/bp/blocks`` and ``schemas/bp/items``, copies the ``schemas/common``
files those reference (when the package ships them) and the package's
``LICENSE``, rewrites the snapshot's row in ``SOURCE.md`` (version, the
package's ``gitHead`` commit, npm publish date), and reports which files and
which block components were added, removed or changed. Prereleases need
``--allow-prerelease``. Nothing here runs during conversion or validation.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import posixpath
import re
import shutil
import tarfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .schema import SCHEMA_ROOT

PACKAGE = "@minecraft/bedrock-schemas"
REGISTRY_URL = "https://registry.npmjs.org/@minecraft%2Fbedrock-schemas"
SOURCE_MD = SCHEMA_ROOT / "SOURCE.md"
VENDORED_DIRS = ("bp/blocks", "bp/items")
BLOCK_COMPONENTS = "bp/blocks/block_components.schema.json"
_USER_AGENT = "anchapin/portkit-v2 schema check (github.com/anchapin/portkit-v2)"
_ROW = re.compile(
    r"^\| `(?P<snapshot>[0-9.]+)/` \| `@minecraft/bedrock-schemas` (?P<version>\S+) "
    r"\| `(?P<commit>[0-9a-f]{40})` \| (?P<date>\d{4}-\d{2}-\d{2}) \|$"
)
_COMMON_REF = re.compile(r'"\$ref"\s*:\s*"((?:\.\./)+common/[^"#]+)')


class SchemaUpstreamError(Exception):
    """The registry or a tarball could not be read, or SOURCE.md is malformed."""


@dataclass(frozen=True)
class Pin:
    snapshot: str
    version: str
    commit: str
    date: str


@dataclass(frozen=True)
class Status:
    snapshot: str
    pinned: str
    state: str  # current | refresh | waiting
    stable: str | None  # the stable package for the snapshot's version, if out
    latest_stable: str | None
    newest_prerelease: str | None
    newer_stable: str | None  # a stable release above the snapshot's version

    @property
    def action_needed(self) -> bool:
        return self.state == "refresh"

    def message(self) -> str:
        if self.state == "current":
            text = f"{self.snapshot}: current ({PACKAGE} {self.pinned} is the stable release)"
        elif self.state == "refresh":
            text = (f"{self.snapshot}: REFRESH DUE: stable {self.stable} is out; vendored {self.pinned}. "
                    f"Run `portkit schemas refresh --snapshot {self.snapshot}`")
        else:
            text = (f"{self.snapshot}: waiting: no stable {self.snapshot} yet (vendored {self.pinned}; "
                    f"latest stable {self.latest_stable or 'none'}, newest {self.snapshot} prerelease "
                    f"{self.newest_prerelease or 'none'})")
        if self.newer_stable:
            text += f"; stable {self.newer_stable} is newer than this snapshot (a new snapshot to add)"
        return text


@dataclass
class RefreshResult:
    snapshot: str
    old_version: str
    new_version: str
    commit: str
    date: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    components_added: list[str] = field(default_factory=list)
    components_removed: list[str] = field(default_factory=list)
    common_copied: list[str] = field(default_factory=list)
    common_missing: list[str] = field(default_factory=list)
    dry_run: bool = False

    def lines(self) -> list[str]:
        verb = "would re-vendor" if self.dry_run else "re-vendored"
        out = [f"{verb} {self.snapshot}/ from {PACKAGE} {self.new_version} "
               f"(was {self.old_version}; gitHead {self.commit[:12]}, published {self.date})",
               f"files: {len(self.added)} added, {len(self.removed)} removed, {len(self.changed)} changed"]
        for label, names in (("added", self.added), ("removed", self.removed), ("changed", self.changed)):
            out += [f"  {label}: {n}" for n in names]
        out.append("block components added: " + (", ".join(self.components_added) or "none"))
        out.append("block components removed: " + (", ".join(self.components_removed) or "none"))
        if self.common_missing:
            out.append("common refs the package does not ship (accepted as anything): "
                       + ", ".join(self.common_missing))
        return out


# ---------------------------------------------------------------- versions
def parse_version(text: str) -> tuple[tuple[int, ...], str | None]:
    """``"1.26.60-beta.24"`` -> ``((1, 26, 60), "beta.24")``; stable -> pre None."""
    base, _, pre = str(text).partition("-")
    try:
        nums = tuple(int(p) for p in base.split("."))
    except ValueError as exc:
        raise SchemaUpstreamError(f"not a package version: {text!r}") from exc
    return nums, (pre or None)


def is_stable(version: str) -> bool:
    return parse_version(version)[1] is None


def _pre_key(pre: str) -> tuple:
    # semver prerelease order: numeric identifiers numerically, others as text
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))


def _sort_key(version: str) -> tuple:
    nums, pre = parse_version(version)
    return (nums, 1 if pre is None else 0, _pre_key(pre) if pre else ())


# ---------------------------------------------------------------- SOURCE.md
def pins(source_md: Path = SOURCE_MD) -> list[Pin]:
    rows = [m.groupdict() for line in Path(source_md).read_text(encoding="utf-8").splitlines()
            if (m := _ROW.match(line.strip()))]
    if not rows:
        raise SchemaUpstreamError(f"{source_md}: no snapshot rows in the expected format")
    return [Pin(**r) for r in rows]


def _write_pin(source_md: Path, pin: Pin) -> None:
    lines = Path(source_md).read_text(encoding="utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        m = _ROW.match(line.strip())
        if m and m["snapshot"] == pin.snapshot:
            lines[i] = (f"| `{pin.snapshot}/` | `{PACKAGE}` {pin.version} | `{pin.commit}` | {pin.date} |"
                        + ("\n" if line.endswith("\n") else ""))
            Path(source_md).write_text("".join(lines), encoding="utf-8")
            return
    raise SchemaUpstreamError(f"{source_md}: no row for snapshot {pin.snapshot}")


# ---------------------------------------------------------------- registry
def fetch_packument(opener: Callable = urllib.request.urlopen, url: str = REGISTRY_URL) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "application/json"})
    try:
        with opener(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise SchemaUpstreamError(f"{url}: {exc}") from exc


def status(pin: Pin, packument: dict) -> Status:
    snap = parse_version(pin.snapshot)[0]
    versions = sorted(packument.get("versions") or {}, key=_sort_key)
    stables = [v for v in versions if is_stable(v)]
    same = [v for v in stables if parse_version(v)[0] == snap]
    pres = [v for v in versions if not is_stable(v) and parse_version(v)[0] == snap]
    newer = [v for v in stables if parse_version(v)[0] > snap]
    if is_stable(pin.version) and parse_version(pin.version)[0] == snap:
        state = "current"
    elif same:
        state = "refresh"
    else:
        state = "waiting"
    return Status(
        snapshot=pin.snapshot,
        pinned=pin.version,
        state=state,
        stable=same[-1] if same else None,
        latest_stable=stables[-1] if stables else None,
        newest_prerelease=pres[-1] if pres else None,
        newer_stable=newer[-1] if newer else None,
    )


def check(packument: dict, source_md: Path = SOURCE_MD) -> list[Status]:
    return [status(p, packument) for p in pins(source_md)]


def _verify(data: bytes, dist: dict, version: str) -> None:
    integrity = dist.get("integrity") or ""
    if integrity.startswith("sha512-"):
        want = base64.b64decode(integrity[len("sha512-"):])
        if hashlib.sha512(data).digest() != want:
            raise SchemaUpstreamError(f"{PACKAGE} {version}: tarball sha512 does not match the registry")
    elif dist.get("shasum"):
        if hashlib.sha1(data).hexdigest() != dist["shasum"]:
            raise SchemaUpstreamError(f"{PACKAGE} {version}: tarball sha1 does not match the registry")
    else:
        raise SchemaUpstreamError(f"{PACKAGE} {version}: registry gives no integrity hash")


def fetch_tarball(packument: dict, version: str, opener: Callable = urllib.request.urlopen) -> bytes:
    meta = (packument.get("versions") or {}).get(version)
    if not meta:
        raise SchemaUpstreamError(f"{PACKAGE} has no version {version}")
    dist = meta.get("dist") or {}
    url = dist.get("tarball")
    if not url:
        raise SchemaUpstreamError(f"{PACKAGE} {version}: no tarball url")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with opener(request, timeout=120) as response:
            data = response.read()
    except OSError as exc:
        raise SchemaUpstreamError(f"{url}: {exc}") from exc
    _verify(data, dist, version)
    return data


# ---------------------------------------------------------------- refresh
def _package_files(tarball: bytes) -> dict[str, bytes]:
    """Every regular file in an npm tarball, keyed by path under ``package/``."""
    out: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                name = posixpath.normpath(member.name)
                if not name.startswith("package/") or ".." in name.split("/"):
                    continue
                out[name[len("package/"):]] = tar.extractfile(member).read()
    except (tarfile.TarError, OSError) as exc:
        raise SchemaUpstreamError(f"not a readable npm tarball: {exc}") from exc
    return out


def _components(files: dict[str, bytes]) -> set[str]:
    raw = files.get(BLOCK_COMPONENTS)
    if raw is None:
        return set()
    return set(json.loads(raw.decode("utf-8")).get("properties") or {})


def refresh(
    snapshot: str,
    version: str,
    tarball: bytes,
    commit: str,
    date: str,
    *,
    root: Path = SCHEMA_ROOT,
    source_md: Path = SOURCE_MD,
    dry_run: bool = False,
) -> RefreshResult:
    """Re-vendor ``root/<snapshot>`` from an npm tarball of ``version``."""
    current = {p.snapshot: p for p in pins(source_md)}
    if snapshot not in current:
        raise SchemaUpstreamError(f"{source_md}: no row for snapshot {snapshot} (add the row first)")
    pkg = _package_files(tarball)
    new: dict[str, bytes] = {}
    for sub in VENDORED_DIRS:
        prefix = f"schemas/{sub}/"
        picked = {k[len("schemas/"):]: v for k, v in pkg.items() if k.startswith(prefix)}
        if not picked:
            raise SchemaUpstreamError(f"{PACKAGE} {version}: tarball has no schemas/{sub}/")
        new.update(picked)
    if BLOCK_COMPONENTS not in new:
        raise SchemaUpstreamError(f"{PACKAGE} {version}: tarball has no schemas/{BLOCK_COMPONENTS}")
    # schemas/common files the vendored schemas point at
    wanted: set[str] = set()
    for rel, raw in new.items():
        for ref in _COMMON_REF.findall(raw.decode("utf-8", "replace")):
            wanted.add(posixpath.normpath(posixpath.join(posixpath.dirname(rel), ref)))
    copied, missing = [], []
    for rel in sorted(wanted):
        if f"schemas/{rel}" in pkg:
            new[rel] = pkg[f"schemas/{rel}"]
            copied.append(rel)
        else:
            missing.append(rel)
    if "LICENSE" in pkg:
        new["LICENSE"] = pkg["LICENSE"]

    snap_dir = Path(root) / snapshot
    old: dict[str, bytes] = {}
    for sub in (*VENDORED_DIRS, "common"):
        base = snap_dir / sub
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    old[path.relative_to(snap_dir).as_posix()] = path.read_bytes()
    if (snap_dir / "LICENSE").is_file():
        old["LICENSE"] = (snap_dir / "LICENSE").read_bytes()

    result = RefreshResult(
        snapshot=snapshot,
        old_version=current[snapshot].version,
        new_version=version,
        commit=commit,
        date=date,
        added=sorted(set(new) - set(old)),
        # common/ files no ref names any more are kept: they cost nothing and
        # may be picked up again (only bp/ is mirrored exactly)
        removed=sorted(k for k in set(old) - set(new) if k.startswith("bp/")),
        changed=sorted(k for k in set(new) & set(old) if new[k] != old[k]),
        components_added=sorted(_components(new) - _components(old)),
        components_removed=sorted(_components(old) - _components(new)),
        common_copied=copied,
        common_missing=missing,
        dry_run=dry_run,
    )
    if dry_run:
        return result
    for sub in VENDORED_DIRS:
        shutil.rmtree(snap_dir / sub, ignore_errors=True)
    for rel, raw in new.items():
        target = snap_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    _write_pin(source_md, Pin(snapshot, version, commit, date))
    return result


def refresh_from_registry(
    snapshot: str,
    version: str | None,
    packument: dict,
    *,
    allow_prerelease: bool = False,
    tarball: bytes | None = None,
    opener: Callable = urllib.request.urlopen,
    root: Path = SCHEMA_ROOT,
    source_md: Path = SOURCE_MD,
    dry_run: bool = False,
) -> RefreshResult:
    """Pick the version (default: the stable release of ``snapshot``), fetch and re-vendor."""
    if version is None:
        st = status(Pin(snapshot, "0.0.0-none", "0" * 40, "0000-00-00"), packument)
        if not st.stable:
            raise SchemaUpstreamError(
                f"no stable {PACKAGE} {snapshot} yet (newest {snapshot} prerelease: "
                f"{st.newest_prerelease or 'none'}); pass --version with --allow-prerelease to vendor one")
        version = st.stable
    if not is_stable(version) and not allow_prerelease:
        raise SchemaUpstreamError(f"{version} is a prerelease; pass --allow-prerelease to vendor it")
    if parse_version(version)[0] != parse_version(snapshot)[0]:
        raise SchemaUpstreamError(
            f"{version} is not a {snapshot} release; a different version is a new snapshot directory")
    meta: dict[str, Any] = (packument.get("versions") or {}).get(version) or {}
    if not meta:
        raise SchemaUpstreamError(f"{PACKAGE} has no version {version}")
    if tarball is None:
        tarball = fetch_tarball(packument, version, opener)
    else:
        _verify(tarball, meta.get("dist") or {}, version)
    commit = meta.get("gitHead") or ""
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SchemaUpstreamError(f"{PACKAGE} {version}: registry gives no gitHead commit")
    date = str((packument.get("time") or {}).get(version) or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise SchemaUpstreamError(f"{PACKAGE} {version}: registry gives no publish date")
    return refresh(snapshot, version, tarball, commit, date, root=root, source_md=source_md, dry_run=dry_run)
