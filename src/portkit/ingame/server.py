"""Run converted packs on a Bedrock Dedicated Server and read the result (#238).

The server is Mojang's, downloaded from minecraft.net, never committed or
redistributed. Downloading it means agreeing to the Minecraft End User License
Agreement and the Microsoft Privacy Statement: the download page puts the
DOWNLOAD button behind "I agree to the Minecraft End User License Agreement and
Privacy Policy" (minecraft.net/en-us/download/server/bedrock, read
2026-10-15). So ``fetch`` refuses unless the caller passes ``accept_eula`` (the
CLI's ``--accept-eula``); the workflow that passes it is where that choice is
made (docs/decisions.md, 2026-10-15, #238).

The server ships for x86-64 Linux (Ubuntu 22.04 or later) and Windows only.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import nbt
from .testpack import write_test_pack

# The pinned server: one release, its Linux zip and that zip's sha256, so a new
# release can't change the checks unannounced. 1.26.52.3 is the release the
# download page offered on 2026-10-15 (and the one the download links API,
# net-secondary.web.minecraft-services.net/api/v1.0/download/links, named).
BDS_VERSION = "1.26.52.3"
BDS_URL = f"https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-{BDS_VERSION}.zip"
# sha256 first read by the six branch runs of 2026-10-15 (Actions run 38837767733),
# all six downloads agreeing.
BDS_SHA256 = "f6348d84fa714d04ca194f207e89453ca6bba0a1359396475271a52a150471c6"

# minecraft.net's CDN holds a request open and drops it unless the User-Agent
# starts like a browser's (checked 2026-10-15: "curl/..." and a bare tool name
# get no response; "Mozilla/5.0 (X11; Linux x86_64) ..." gets the zip). The
# rest of the string still says who is asking (a URL in it gets dropped too).
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) portkit-ingame"

EULA_URL = "https://minecraft.net/eula"
PRIVACY_URL = "https://www.microsoft.com/en-us/privacy/privacystatement"

LEVEL = "portkit"
TAG = "PORTKIT-INGAME"

# server.properties for a check run: a flat creative world nobody joins, with
# the content log on and printed, cheats on (the check script adds a ticking
# area), and no client-side packs forced.
PROPERTIES = {
    "level-name": LEVEL,
    "level-type": "FLAT",
    "level-seed": "238",
    "gamemode": "creative",
    "difficulty": "peaceful",
    "allow-cheats": "true",
    "max-players": "1",
    "content-log-file-enabled": "true",
    "content-log-console-output-enabled": "true",
    "content-log-level": "info",
    "texturepack-required": "false",
}


class EulaNotAccepted(RuntimeError):
    pass


def fetch(dest: Path, accept_eula: bool, url: str = BDS_URL, sha256: str = BDS_SHA256) -> Path:
    """Download and unpack the pinned server into ``dest``; return ``dest``."""
    if not accept_eula:
        raise EulaNotAccepted(
            "downloading Bedrock Dedicated Server means agreeing to the Minecraft EULA "
            f"({EULA_URL}) and the Microsoft Privacy Statement ({PRIVACY_URL}); "
            "pass --accept-eula to agree"
        )
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest.parent / f"{dest.name}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=300) as resp, archive.open("wb") as fh:
        while chunk := resp.read(1 << 20):
            digest.update(chunk)
            fh.write(chunk)
    got = digest.hexdigest()
    print(f"bedrock-server {BDS_VERSION}: sha256 {got}")
    if not sha256:
        archive.unlink()
        raise ValueError(f"no sha256 pinned for {url}; downloaded file is {got}")
    if got != sha256:
        archive.unlink()
        raise ValueError(f"sha256 mismatch for {url}: expected {sha256}, got {got}")
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)
    archive.unlink()
    binary = dest / "bedrock_server"
    if binary.exists():
        binary.chmod(0o755)
    return dest


def set_properties(text: str, values: dict[str, str]) -> str:
    """server.properties text with ``values`` set (replaced in place, else appended)."""
    lines = text.splitlines()
    seen = set()
    for i, raw in enumerate(lines):
        key = raw.split("=", 1)[0].strip()
        if not raw.lstrip().startswith("#") and "=" in raw and key in values:
            lines[i] = f"{key}={values[key]}"
            seen.add(key)
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def _pack_ref(pack: Path) -> dict:
    header = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))["header"]
    return {"pack_id": header["uuid"], "version": header["version"]}


@dataclass
class Prepared:
    root: Path
    behavior: list[Path] = field(default_factory=list)
    resource: list[Path] = field(default_factory=list)


def prepare(server: Path, work: Path, tree: Path, name: str) -> Prepared:
    """A fresh server copy in ``work`` with the converted tree and its check pack."""
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(server, work, symlinks=True)
    props = work / "server.properties"
    props.write_text(set_properties(props.read_text() if props.exists() else "", PROPERTIES))
    prepared = Prepared(work)
    bp_src, rp_src = tree / "behavior_pack", tree / "resource_pack"
    if bp_src.is_dir():
        dest = work / "behavior_packs" / f"portkit_{name}"
        shutil.copytree(bp_src, dest)
        prepared.behavior.append(dest)
    if rp_src.is_dir():
        dest = work / "resource_packs" / f"portkit_{name}"
        shutil.copytree(rp_src, dest)
        prepared.resource.append(dest)
    check = work / "behavior_packs" / f"portkit_checks_{name}"
    write_test_pack(bp_src, check, name)
    prepared.behavior.append(check)
    world = work / "worlds" / LEVEL
    world.mkdir(parents=True, exist_ok=True)
    (world / "world_behavior_packs.json").write_text(
        json.dumps([_pack_ref(p) for p in prepared.behavior], indent=2) + "\n"
    )
    (world / "world_resource_packs.json").write_text(
        json.dumps([_pack_ref(p) for p in prepared.resource], indent=2) + "\n"
    )
    return prepared


@dataclass
class Run:
    lines: list[str]
    exit_code: int | None
    timed_out: bool
    seconds: float


def run(root: Path, stop_on: str, timeout: float, log: Path | None = None) -> Run:
    """Start the server in ``root``; send ``stop`` once a line contains ``stop_on``."""
    env = dict(os.environ, LD_LIBRARY_PATH=".")
    start = time.monotonic()
    proc = subprocess.Popen(
        ["./bedrock_server"], cwd=root, env=env, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1,
    )
    lines_q: queue.Queue[str | None] = queue.Queue()

    def pump():
        for raw in proc.stdout:
            lines_q.put(raw.rstrip("\n"))
        lines_q.put(None)

    threading.Thread(target=pump, daemon=True).start()
    lines: list[str] = []
    timed_out = stopping = False
    sink = log.open("w", encoding="utf-8") if log else None
    try:
        while True:
            left = timeout - (time.monotonic() - start)
            if left <= 0:
                timed_out = True
                break
            try:
                item = lines_q.get(timeout=min(left, 5))
            except queue.Empty:
                continue
            if item is None:
                break
            lines.append(item)
            if sink:
                sink.write(item + "\n")
                sink.flush()
            if not stopping and stop_on in item:
                stopping = True
                proc.stdin.write("stop\n")
                proc.stdin.flush()
    finally:
        if sink:
            sink.close()
    if timed_out or proc.poll() is None:
        try:
            if not stopping:
                proc.stdin.write("stop\n")
                proc.stdin.flush()
            proc.wait(timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait()
    return Run(lines, proc.returncode, timed_out, round(time.monotonic() - start, 1))


def enable_experiments(root: Path, names: list[str], timeout: float = 120) -> None:
    """Boot once so the world (and its level.dat) exists, then toggle ``names`` on."""
    first = run(root, "Server started.", timeout)
    level = root / "worlds" / LEVEL / "level.dat"
    if not level.exists():
        raise RuntimeError("the first boot wrote no level.dat:\n" + "\n".join(first.lines[-30:]))
    level.write_bytes(nbt.with_experiments(level.read_bytes(), names))


_SEVERITY = re.compile(r"\b(ERROR|WARN(?:ING)?)\]|\[(error|warning)\]", re.IGNORECASE)


def parse(lines: list[str]) -> dict:
    """The tagged check lines and the server's errors and warnings, from its output."""
    tagged: list[tuple[str, dict]] = []
    errors: list[str] = []
    warnings: list[str] = []
    for raw in lines:
        at = raw.find(TAG + " ")
        if at >= 0:
            rest = raw[at + len(TAG) + 1:]
            kind, _, payload = rest.partition(" ")
            try:
                data = json.loads(payload) if payload else {}
            except ValueError:
                data = {"raw": payload}
            tagged.append((kind, data))
            continue
        m = _SEVERITY.search(raw)
        if not m:
            continue
        level = (m.group(1) or m.group(2)).upper()
        (errors if level == "ERROR" else warnings).append(raw)
    summary = next((d for k, d in reversed(tagged) if k == "SUMMARY"), None)
    return {
        "done": any(k == "DONE" for k, _ in tagged),
        "start": next((d for k, d in tagged if k == "START"), None),
        "summary": summary,
        "failures": [d for k, d in tagged if k == "FAIL"],
        "script_errors": [d for k, d in tagged if k == "ERROR"],
        "connections": [d for k, d in tagged if k == "CONNECTION"],
        "content_errors": errors,
        "content_warnings": warnings,
    }


def verdict(report: dict) -> list[str]:
    """Why a run fails, empty when it passes."""
    why = []
    if not report["done"]:
        why.append("the check script never finished")
    if report["script_errors"]:
        why.append(f"{len(report['script_errors'])} check script error(s)")
    if report["failures"]:
        why.append(f"{len(report['failures'])} failed check(s)")
    if report["content_errors"]:
        why.append(f"{len(report['content_errors'])} content-log error(s)")
    return why


def collect_logs(root: Path, out: Path) -> list[Path]:
    """Copy the server's content-log files (if it wrote any) into ``out``."""
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    for path in sorted(root.rglob("ContentLog*")):
        if path.is_file():
            dest = out / path.name
            shutil.copyfile(path, dest)
            copied.append(dest)
    return copied
