"""``mekanism:mod_version_loaded``, evaluated by the mekanism adapter (#245)."""
from portkit import adapters
from portkit.adapters import mekanism
from portkit.conditions import LoadContext
from portkit.model import SourceMod


def _context(tmp_path):
    (tmp_path / "data" / "examplemod").mkdir(parents=True)
    return LoadContext(SourceMod(root=tmp_path, namespace="examplemod", loader="neoforge",
                                 mods={"examplemod": "1.0"}, requires=frozenset({"mekanism"})))


def test_registered():
    assert mekanism.ADAPTER in adapters.ADAPTERS
    assert adapters.condition_handler("mekanism:mod_version_loaded") is mekanism.mod_version_loaded


def test_absent_mod_is_false_and_a_loaded_one_undecidable(tmp_path):
    context = _context(tmp_path)
    kind = "mekanism:mod_version_loaded"
    absent = context.evaluate([{"type": kind, "modid": "othermod", "version": "2.0"}])
    assert (absent.passes, absent.why, absent.absent) == (False, f"{kind} othermod", ["othermod"])
    loaded = context.evaluate([{"type": kind, "modid": "mekanism", "version": "10.7"}])
    assert (loaded.passes, loaded.why) == (None, f"{kind} mekanism >= 10.7 on a loaded mod")
