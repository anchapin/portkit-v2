"""TEMPORARY (#372 profiling, reverted before merge): timing of a convert.

Prints to stderr, at exit, the time per registration run (_registered) split
into its passes and its build loop, the time per converter, a sampled
profile of Python frames, and the Java methods run most."""
from __future__ import annotations

import atexit
import collections
import os
import sys
import threading
import time

_t0 = time.time()
_main = threading.get_ident()
_cum = collections.Counter()
_self = collections.Counter()
_n = [0]
_phase = collections.Counter()
_reg_calls: list = []
_java_self = collections.Counter()
_java_calls = collections.Counter()
_java_lib = {}
_stack: list = []


def _key(fr):
    c = fr.f_code
    return f"{os.path.basename(c.co_filename)}:{c.co_firstlineno}:{c.co_name}"


def _sampler():
    while True:
        time.sleep(0.02)
        fr = sys._current_frames().get(_main)
        if fr is None:
            continue
        _n[0] += 1
        seen = set()
        _self[_key(fr)] += 1
        while fr is not None:
            k = _key(fr)
            if k not in seen:
                _cum[k] += 1
                seen.add(k)
            fr = fr.f_back


def install():
    from portkit import blockcode
    orig_run = blockcode.Machine.run

    def run(self, cf, m, a):
        key = f"{cf.name}.{m.name}"
        _java_calls[key] += 1
        _java_lib[key] = bool(self._library(cf.name))
        s0 = self.steps
        _stack.append([key, 0])
        try:
            return orig_run(self, cf, m, a)
        finally:
            k, child = _stack.pop()
            incl = max(self.steps - s0, 0)
            _java_self[k] += max(incl - child, 0)
            if _stack:
                _stack[-1][1] += incl

    blockcode.Machine.run = run
    orig_reg = blockcode._registered
    orig_census = blockcode._census

    def _census(machine):
        t = time.time()
        try:
            return orig_census(machine)
        finally:
            _phase["census_s"] += time.time() - t

    blockcode._census = _census

    def _set_regs(self, v):
        old = self.__dict__.get("_regs")
        if v is None and old is not None and _reg_calls and _reg_calls[-1].get("open"):
            _reg_calls[-1]["passes_s"] = round(time.time() - _reg_calls[-1]["t"], 1)
            _reg_calls[-1]["regs"] = len(old)
            _reg_calls[-1]["values"] = len({id(r.value) for r in old if r.value is not None})
            _reg_calls[-1]["reg_names"] = len({r.name for r in old})
        self.__dict__["_regs"] = v

    blockcode.Machine.registrations = property(lambda self: self.__dict__.get("_regs"), _set_regs)

    def _registered(classes, names):
        caller = sys._getframe(1)
        rec = {"caller": _key(caller), "names": len(names), "t": time.time(), "open": True}
        _reg_calls.append(rec)
        try:
            return orig_reg(classes, names)
        finally:
            rec["open"] = False
            rec["total_s"] = round(time.time() - rec["t"], 1)
            print(f"[prof372] _registered {rec}", file=sys.stderr, flush=True)

    blockcode._registered = _registered
    # Callers that imported the name directly.
    for modname, mod in list(sys.modules.items()):
        if modname.startswith("portkit") and getattr(mod, "_registered", None) is orig_reg and mod is not blockcode:
            mod._registered = _registered
    try:
        from portkit import converters
        orig_all = converters.convert_all
    except Exception:  # noqa: BLE001
        orig_all = None
    threading.Thread(target=_sampler, daemon=True).start()
    atexit.register(report)


def report():
    out = sys.stderr
    print(f"[prof372] elapsed {time.time() - _t0:.1f}s samples {_n[0]}", file=out)
    for k, v in _phase.items():
        print(f"[prof372] phase {k} {v:.1f}", file=out)
    tot = sum(r.get("total_s", 0) for r in _reg_calls)
    print(f"[prof372] _registered calls {len(_reg_calls)} total {tot:.1f}s", file=out)
    for r in _reg_calls:
        print(f"[prof372]   {r}", file=out)
    print("[prof372] python cumulative (samples, 20 ms):", file=out)
    for k, v in _cum.most_common(90):
        print(f"[prof372]   {v} {k}", file=out)
    print("[prof372] python self:", file=out)
    for k, v in _self.most_common(40):
        print(f"[prof372]   {v} {k}", file=out)
    tj = sum(_java_self.values()) or 1
    lib = sum(v for k, v in _java_self.items() if _java_lib.get(k))
    print(f"[prof372] java steps {tj} library {lib}", file=out)
    for k, v in _java_self.most_common(60):
        print(f"[prof372]   {v} {_java_calls[k]} {'L' if _java_lib.get(k) else 'M'} {k}", file=out)
    out.flush()
