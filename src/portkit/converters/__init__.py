"""Deterministic converters.

Every converter is a pure function: SourceMod -> ConversionResult. No network,
no model, no global state. Register it here and it joins the pipeline and the
fixture harness automatically.
"""
from __future__ import annotations

from ..model import ConversionResult, SourceMod
from . import lang, recipes, textures

CONVERTERS = [
    textures.convert,
    recipes.convert,
    lang.convert,
]


def convert_all(mod: SourceMod) -> ConversionResult:
    result = ConversionResult()
    for fn in CONVERTERS:
        result = result.merge(fn(mod))
    return result
