"""pfind regression tests. Run: python -m pytest tests"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PFIND = Path(__file__).resolve().parents[1] / "pfind.py"
needs_rg = pytest.mark.skipif(shutil.which("rg") is None, reason="ripgrep (rg) not installed")


def run(*args, cwd):
    r = subprocess.run([sys.executable, str(PFIND), *args, "--no-color"], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout


@needs_rg
def test_source_in_a_folder_named_build_is_found(tmp_path):
    """2026-09-29: a function defined in fieldkit/build/kernel.py was reported only in its test."""
    (tmp_path / "pkg" / "build").mkdir(parents=True)
    (tmp_path / "pkg" / "build" / "kernel.py").write_text("def verify_fragment():\n    pass\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_kernel.py").write_text("verify_fragment()\n")
    _, out = run("verify_fragment", ".", cwd=tmp_path)
    # match the path, not the name: "test_kernel.py" also contains "kernel.py"
    assert re.search(r"build[\\/]kernel\.py", out), out
    assert "test_kernel.py" in out


@needs_rg
def test_real_noise_is_still_skipped(tmp_path):
    (tmp_path / "obj-x86_64-pc-linux-gnu").mkdir()
    (tmp_path / "obj-x86_64-pc-linux-gnu" / "gen.py").write_text("needle_xyz = 1\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("needle_xyz\n")
    (tmp_path / "real.py").write_text("needle_xyz = 2\n")
    _, out = run("needle_xyz", ".", cwd=tmp_path)
    assert "real.py" in out and "obj-x86_64" not in out and "node_modules" not in out


@needs_rg
def test_gitignored_build_output_is_skipped(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("build/\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.py").write_text("needle_abc = 1\n")
    (tmp_path / "src.py").write_text("needle_abc = 2\n")
    _, out = run("needle_abc", ".", cwd=tmp_path)
    assert "src.py" in out and "out.py" not in out
