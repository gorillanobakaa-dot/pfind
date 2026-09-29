"""pfind tests. Run: python -m pytest tests

Every behaviour is checked with BOTH engines: ripgrep, and the built-in Python engine
(PFIND_NO_RG=1) that a Windows user without ripgrep gets. Each test below was written
from a failure seen on Windows on 2026-09-29, and fails on pfind 2.1.0.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PFIND = Path(__file__).resolve().parents[1] / "pfind.py"
ENGINES = ["python"] + (["ripgrep"] if shutil.which("rg") else [])


def run(*args, cwd, engine="python", stdin=None, env_extra=None):
    env = dict(os.environ)
    env.pop("PFIND_NO_RG", None)
    if engine == "python":
        env["PFIND_NO_RG"] = "1"
    env.update(env_extra or {})
    r = subprocess.run([sys.executable, str(PFIND), *args, "--no-color"], cwd=cwd, capture_output=True,
                       input=stdin, env=env)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def found(out, relpath):
    """Is this file (by its path inside the tree, either slash) in the output?"""
    return re.search(re.escape(relpath).replace("/", r"[\\/]") + r"\b", out) is not None


@pytest.fixture
def tree(tmp_path):
    def put(rel, data):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            p.write_bytes(data)
        else:
            p.write_text(data, encoding="utf-8")   # Windows' default code page cannot hold an emoji
    put("pkg/build/kernel.py", "def verify_fragment():\n    pass\n")
    put("tests/test_kernel.py", "verify_fragment()\n")
    put("win/crlf.py", b"def load_config(path):\r\n    with open(path) as f:\r\n        return json.load(f)\r\n")
    put("notes/emoji.md", "# \U0001F98D gorilla \u4f60\u597d marker_emoji\n")
    put(".hidden/secret.txt", "needle_hidden\n")
    put("blob.pyc", b"needle_bin\x00\x01\x02")
    put("data.bin", b"needle_bin\x00")
    put("Mixed.txt", "Needle_Case here\n")
    put("lower.txt", "needle_case here\n")
    put("obj-x86_64-pc-linux-gnu/gen.py", "needle_obj = 1\n")
    put("node_modules/lib.js", "needle_obj\n")
    put("src/app.py", "needle_obj = 2\n")
    return tmp_path


@pytest.mark.parametrize("engine", ENGINES)
def test_source_in_a_folder_named_build_is_found(tree, engine):
    _, out, _ = run("verify_fragment", ".", cwd=tree, engine=engine)
    assert found(out, "build/kernel.py") and found(out, "test_kernel.py")


@pytest.mark.parametrize("engine", ENGINES)
def test_real_noise_is_still_skipped(tree, engine):
    _, out, _ = run("needle_obj", ".", cwd=tree, engine=engine)
    assert found(out, "src/app.py") and "obj-x86_64" not in out and "node_modules" not in out


@pytest.mark.parametrize("engine", ENGINES)
def test_multiline_snippet_matches_crlf_file(tree, engine):
    snippet = tree / "snippet.txt"
    snippet.write_text("def load_config(path):\n    with open(path) as f:\n")
    rc, out, err = run("--query-file", str(snippet), "-x", ".", cwd=tree, engine=engine)
    assert rc == 0 and found(out, "win/crlf.py"), out + err


@pytest.mark.parametrize("engine", ENGINES)
def test_snippet_from_stdin(tree, engine):
    rc, out, _ = run("-", "-x", ".", cwd=tree, engine=engine,
                     stdin=b"def load_config(path):\n    with open(path) as f:\n")
    assert rc == 0 and found(out, "win/crlf.py")


@pytest.mark.parametrize("engine", ENGINES)
def test_emoji_file_does_not_crash_on_a_legacy_console(tree, engine):
    rc, out, err = run("marker_emoji", ".", cwd=tree, engine=engine, env_extra={"PYTHONIOENCODING": "cp1252"})
    assert rc == 0, err
    assert found(out, "notes/emoji.md") and "\U0001F98D" in out and "Traceback" not in err


@pytest.mark.parametrize("engine", ENGINES)
def test_hidden_skipped_unless_asked(tree, engine):
    _, out, _ = run("needle_hidden", ".", cwd=tree, engine=engine)
    assert "secret.txt" not in out
    _, out, _ = run("needle_hidden", ".", "--hidden", cwd=tree, engine=engine)
    assert found(out, ".hidden/secret.txt")


@pytest.mark.parametrize("engine", ENGINES)
def test_binaries_are_not_searched(tree, engine):
    _, out, _ = run("needle_bin", ".", "--content", cwd=tree, engine=engine)
    assert "blob.pyc" not in out and "data.bin" not in out


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("ext", ["py", ".py"])
def test_ext_with_or_without_dot(tree, engine, ext):
    _, out, _ = run("load_config", ".", "--ext", ext, cwd=tree, engine=engine)
    assert found(out, "win/crlf.py")


@pytest.mark.parametrize("engine", ENGINES)
def test_smart_case_is_the_same_in_both_engines(tree, engine):
    _, out, _ = run("needle_case", ".", "--content", cwd=tree, engine=engine)
    assert found(out, "Mixed.txt") and found(out, "lower.txt")          # lowercase query: any case
    _, out, _ = run("Needle_Case", ".", "--content", cwd=tree, engine=engine)
    assert found(out, "Mixed.txt") and not found(out, "lower.txt")      # capital in query: exact case


@pytest.mark.parametrize("engine", ENGINES)
def test_name_match_ignores_where_the_root_lives(tmp_path, engine):
    root = tmp_path / "zzroot_documents"
    (root / "a").mkdir(parents=True)
    (root / "a" / "report.txt").write_text("x\n")
    rc, out, _ = run("zzroot", str(root), "--names", cwd=tmp_path, engine=engine)
    assert "report.txt" not in out                                       # only the folder above matched
    _, out, _ = run("report", str(root), "--names", cwd=tmp_path, engine=engine)
    assert found(out, "a/report.txt")


@pytest.mark.parametrize("engine", ENGINES)
def test_json_output_for_agents(tree, engine):
    rc, out, _ = run("verify_fragment", ".", "--json", cwd=tree, engine=engine)
    data = json.loads(out)
    assert rc == 0 and data["engine"] == engine and data["matched"] >= 2
    top = data["results"][0]
    assert {"path", "score", "why", "hits", "samples"} <= set(top)
    rc, out, _ = run("nothing_matches_this_zz", ".", "--json", cwd=tree, engine=engine)
    assert rc == 1 and json.loads(out)["results"] == []


def test_doctor_reports_and_never_installs_without_a_person(tmp_path):
    rc, out, _ = run("--doctor", "--json", cwd=tmp_path)
    data = json.loads(out)
    names = {c["name"] for c in data["checks"]}
    assert rc == 0 and {"Python", "ripgrep (rg)"} <= names
    rc, out, _ = run("--doctor", cwd=tmp_path, stdin=b"y\n")          # not a terminal: must not install
    assert rc == 0 and "installed. Open a new terminal" not in out


def test_query_required(tmp_path):
    rc, _, err = run(cwd=tmp_path)
    assert rc == 2 and "query is needed" in err


@pytest.mark.skipif(not shutil.which("rg"), reason="needs ripgrep")
def test_gitignored_build_output_is_skipped_with_ripgrep(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("build/\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.py").write_text("needle_abc = 1\n")
    (tmp_path / "src.py").write_text("needle_abc = 2\n")
    _, out, _ = run("needle_abc", ".", cwd=tmp_path, engine="ripgrep")
    assert found(out, "src.py") and "out.py" not in out
