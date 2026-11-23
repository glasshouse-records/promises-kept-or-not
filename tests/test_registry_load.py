"""registry.load reads the 1 MB institutions.yaml with the C loader and caches it until
the file changes; callers get independent copies (it was 1-2 s per call in tests)."""
import time

import yaml

from glasshouse import registry


def test_same_content_as_the_python_loader():
    with open(registry.CONFIG_PATH) as fh:
        assert registry.load() == yaml.safe_load(fh)["institutions"]


def test_repeat_load_is_fast_and_independent():
    a = registry.load()
    t = time.perf_counter()
    b = registry.load()
    assert time.perf_counter() - t < 0.2
    a[next(iter(a))]["display_name"] = "MUTATED"
    assert registry.load()[next(iter(a))]["display_name"] != "MUTATED"
    assert b is not a


def test_a_changed_file_is_reread(tmp_path):
    p = tmp_path / "i.yaml"
    p.write_text("institutions:\n  x: {display_name: One}\n")
    assert registry.load(p)["x"]["display_name"] == "One"
    p.write_text("institutions:\n  x: {display_name: Two, cik: '1'}\n")
    assert registry.load(p)["x"]["display_name"] == "Two"
