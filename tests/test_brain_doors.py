"""--brain sends nothing and downloads nothing (pfind 2.2.2, 2026-10-20).

Chroma opens two doors on its own: usage telemetry to the vendor, and a download of the
embedding model on first use. The first test reads the code (it runs everywhere); the
second opens a real Chroma store and proves the vendor's telemetry library was never
loaded. It needs a Python with chromadb: PFIND_CHROMA_PYTHON, or the one running the tests.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PFIND = HERE.parent / "pfind.py"


def test_semantic_brain_opens_chroma_only_through_the_door_cutter():
    src = PFIND.read_text(encoding="utf-8")
    body = src[src.index("def semantic_brain("):]
    body = body[: body.index("\ndef ", 1)]
    assert "_cut_chroma_doors()" in body, "semantic_brain imports chromadb directly again"
    assert "import chromadb" not in body, "a bare import chromadb opens the telemetry door"
    assert "settings=Settings(**settings)" in body and "embedding_function=LocalModelOnly()" in body


PROBE = r"""
import importlib.util, sys, tempfile
spec = importlib.util.spec_from_file_location("pfind", sys.argv[1])
pfind = importlib.util.module_from_spec(spec); spec.loader.exec_module(pfind)
chromadb, settings, LocalModelOnly = pfind._cut_chroma_doors()
from chromadb.config import Settings  # telemetry-ok: the probe opens Chroma through the door cutter
client = chromadb.PersistentClient(path=tempfile.mkdtemp(), settings=Settings(**settings))
col = client.create_collection("probe", embedding_function=None)
col.add(ids=["a"], embeddings=[[0.1, 0.2, 0.3]], documents=["x"])
loaded = sorted(m for m in sys.modules if "posthog" in m.lower())  # telemetry-ok: proves the vendor library never loaded
try:
    LocalModelOnly()._download("https://example.invalid/model.tar.gz", "m")
    downloaded = "yes"
except RuntimeError:
    downloaded = "refused"
print("LOADED", loaded, "DOWNLOAD", downloaded)
"""


def _python_with_chromadb():
    for py in (os.environ.get("PFIND_CHROMA_PYTHON"), sys.executable):
        if py and subprocess.run([py, "-c", "import chromadb"], capture_output=True).returncode == 0:
            return py
    return None


def test_a_real_chroma_store_loads_no_telemetry_and_downloads_nothing(tmp_path):
    py = _python_with_chromadb()
    if py is None:
        pytest.skip("no Python with chromadb (set PFIND_CHROMA_PYTHON)")
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", NO_PROXY="")
    r = subprocess.run([py, "-c", PROBE, str(PFIND)], capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr[-1500:]
    assert "LOADED [] DOWNLOAD refused" in r.stdout, r.stdout + r.stderr[-800:]
