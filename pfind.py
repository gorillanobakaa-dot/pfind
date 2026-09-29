#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# pfind — hybrid local search (filename + content + fuzzy + exact-snippet + semantic).
# Copyright (C) 2026  gorillanobakaa
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along
# with this program. If not, see <https://www.gnu.org/licenses/>.
#
# The deal (copyleft, in one line): use it, fork it, change it, sell it — but any
# version you SHIP or RUN AS A SERVICE must stay open under this same license, so
# every improvement can flow back and the tool keeps growing. Improvements welcome
# upstream: https://github.com/gorillanobakaa-dot/pfind
#
# VERSION: 2.2.0 | UPDATED: 2026-09-29 | STATUS: live
# CHANGELOG:
#   2.2.0 (2026-09-29) — Windows port (same file runs on Windows and Linux). (1) Output
#       from ripgrep is decoded as UTF-8: a file holding an emoji crashed the search on a
#       Windows code page. stdout/stderr never crash on a legacy console; ANSI colour is
#       switched on through the console API or left off. (2) CRLF: a pasted multi-line
#       snippet matches files with Windows line endings (\n in the snippet = \r?\n).
#       (3) The no-ripgrep fallback now equals the rg engine: file-name excludes, hidden
#       folders skipped unless --hidden, binaries skipped, smart-case, multi-line
#       snippets, coverage ranking. (4) "build"/"dist" no longer excluded (they hid real
#       source). (5) Name matching scores the path INSIDE the search root, not C:\Users\..
#       (6) Presets from a config file (~/.config/pfind/presets.json or
#       %APPDATA%\pfind\presets.json); CPU count detected. (7) --query-file FILE / "-"
#       (stdin) for snippets a shell cannot quote; --json for agents; PFIND_NO_RG=1 forces
#       the fallback; pfind.cmd launcher.
#   2.1.0 (2026-07-22) — Needle-in-a-haystack-of-needles upgrade. (1) EXACT MULTI-LINE
#       snippet search: paste a remembered code block (newlines and all) and pfind finds
#       it literally via `rg -U -F`; --loose tolerates whitespace/indent drift. Designed
#       to survive total loss of the memory tiers — the raw files ARE the fallback index.
#       (2) Ranking fix: content ranked by DISTINCT query-terms matched (coverage), not
#       raw hit-count, so a 1-line config beats a 274-hit source file; weighted RRF boosts
#       name/semantic over content. Fixes the wifi-regdom test where verify.sh ranked #9.
#   2.0.0 (2026-07-22) — Full rewrite. Hybrid search: filename + content + fuzzy,
#       fused with Reciprocal Rank Fusion (RRF) into ONE ranked, grouped result.
#       Engine delegates to ripgrep (SIMD, multithreaded, gitignore-aware) with a
#       pure-Python fallback so it never hard-fails. Architecture-aware roots
#       (--brain/--work/--src/--all) + noise-aware default excludes. Opt-in
#       --brain semantic seam over the Chroma Second Brain (degrades to lexical).
#       Supersedes the 1.x pure-Python re+mmap parallel grep.
#   1.0.0 — original parallel mmap+re grep (backed up in scratchpad pre-rewrite).
#
# RULE (per toolkit versioning convention): to change this tool, EDIT this file and
# bump VERSION + add a CHANGELOG line. NEVER spawn pfind_v3 / pfind_new / a copy.
"""
pfind — find stuff, ranked, in one shot.

Why this exists (the roadblock it kills):
    Through the whole toolkit-consolidation work we kept searching ONE dimension at a
    time — filenames OR content, exact OR meaning — and paid for it (the day an agent
    renamed setup_orchestrator.py -> build.py and a filename-only grep missed the real
    monolith sitting in modules/). pfind searches NAME and CONTENT together, ranks with
    the same scale-invariant fusion (RRF) that production hybrid search uses, and shows
    you the few files that actually matter instead of 400 raw grep lines.

    It is NOT a faster grep — ripgrep already won that. pfind is the smart front-end on
    top of ripgrep: multi-signal, ranked, architecture-aware, and honest about *why*
    each hit ranked where it did.

Machine tuning (gorilla-sve14a3aj — Sony VAIO SVE, i7-3632QM):
    - 8 logical CPUs (4C/8T). ripgrep auto-saturates them; --workers overrides its
      thread count. The old 1.x tuning (mmap zero-copy, manual 8-way sharding) is now
      ripgrep's job — it does it better and in SIMD.
    - Default excludes are tuned to THIS tree's noise: firefox objdirs, .mozbuild, the
      18 GB Chroma binary stores, node_modules, vector_env, editor caches.

Quick start:
    pfind setup_orchestrator            # name + content, ranked, across cwd
    pfind run_gpu_liberator --work      # search the FIREFOX.WORK toolkit
    pfind "hardware_only_mode" --all    # brain + work + firefox-main, one shot
    pfind deploy.sh --names             # filename hits only
    pfind "VA-API" --content -C 2       # content hits only, with context lines
    pfind orchestr --fuzzy              # typo/partial-tolerant name match
    pfind "how do we fix the black window" --brain   # semantic over the Second Brain

Presets (architecture roots; defaults below, override in presets.json):
    --brain  -> ~/Documents/SECOND.BRAIN          (also enables semantic seam)
    --work   -> ~/Documents/FIREFOX.WORK          (the toolkit + patches)
    --src    -> ~/firefox-main                     (the Firefox source tree)
    --all    -> brain + work + src
    presets.json lives in ~/.config/pfind/ (Linux/macOS) or %APPDATA%\\pfind\\ (Windows):
        {"brain": "D:/notes", "work": "~/Documents/work", "src": "~/src/firefox"}

Windows:
    Works the same. Install ripgrep for full speed (winget install BurntSushi.ripgrep.MSVC,
    or scoop install ripgrep); without it pfind uses its built-in Python engine.
    Multi-line snippets are hard to type in cmd.exe: save the snippet to a file and run
    pfind --query-file snippet.txt -x   (or pipe it:  type snippet.txt | pfind - -x)

Output: files ranked best-first. Each line shows the RRF score, WHY it ranked
(name-match / N content hits / semantic), and the path; content samples follow.
"""

import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

# ---------------------------------------------------------------------------
# Machine / architecture constants
# ---------------------------------------------------------------------------
IS_WINDOWS = os.name == "nt"
LOGICAL_CPUS = os.cpu_count() or 4

HOME = Path.home()
PRESET_ROOTS = {
    "brain": HOME / "Documents" / "SECOND.BRAIN",
    "work":  HOME / "Documents" / "FIREFOX.WORK",
    "src":   HOME / "firefox-main",
}


def _preset_file():
    base = os.environ.get("APPDATA") if IS_WINDOWS else os.environ.get("XDG_CONFIG_HOME")
    return Path(base or (HOME / ".config")) / "pfind" / "presets.json"


def _load_presets():
    """presets.json overrides the default roots: {"brain": "path", ...}."""
    f = _preset_file()
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except (OSError, ValueError) as e:
        print(f"pfind: ignoring {f}: {e}", file=sys.stderr)
        return
    for name, raw in data.items():
        if name in PRESET_ROOTS and isinstance(raw, str):
            PRESET_ROOTS[name] = Path(os.path.expandvars(raw)).expanduser()


_load_presets()
BRAIN_CHROMA = Path(os.environ.get("PFIND_BRAIN_DB") or
                    PRESET_ROOTS["brain"] / "Chroma.DB.and.Brain.xml" / "chroma_db")
BRAIN_DEFAULT_COLLECTION = "core_memory"  # 91k docs; the firefox/IT working memory

# Noise this tree is full of. Passed to ripgrep as !globs and used by the fallback.
EXCLUDE_GLOBS = [
    ".git", ".hg", ".svn", "node_modules", "__pycache__",
    ".mozbuild", "venv", ".venv", "vector_env",
    # NOT "build"/"dist": real source lives in folders with those names
    # (fieldkit/build/, pkg/build/). A blanket skip hid them and pfind said
    # "not found" with confidence. Build OUTPUT is caught by obj-* below and by
    # .gitignore, which ripgrep honours; add --exclude build to skip it by hand.
    "obj-*",                       # firefox objdirs: obj-x86_64-pc-linux-gnu
    "chroma_db", "chroma_fx154",   # the big vector stores
    "*.sqlite3", "*.bin", "*.parquet", "*.pyc",
    "*.min.js", "*.map",
]

RRF_K_DEFAULT = 60  # standard; small corpora sharpen with lower k (20-30)


# ---------------------------------------------------------------------------
# Root resolution
# ---------------------------------------------------------------------------
def resolve_roots(paths, presets):
    roots = []
    for name in presets:
        p = PRESET_ROOTS[name]
        if p.exists():
            roots.append(p)
        else:
            print(f"pfind: preset --{name} path missing: {p}", file=sys.stderr)
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if p.exists():
            roots.append(p)
        else:
            print(f"pfind: path does not exist: {p}", file=sys.stderr)
    if not roots:
        roots = [Path.cwd()]
    # de-dup while preserving order
    seen, out = set(), []
    for r in roots:
        rs = str(r)
        if rs not in seen:
            seen.add(rs)
            out.append(r)
    return out


def rg_common_globs(ext_filter, extra_excludes, include_hidden, no_ignore):
    globs = []
    for g in EXCLUDE_GLOBS:
        globs += ["-g", f"!{g}"]
    for g in extra_excludes:
        globs += ["-g", f"!{g}"]
    if ext_filter:
        for e in ext_filter:
            e = e if e.startswith(".") else "." + e
            globs += ["-g", f"*{e}"]
    return globs


# ---------------------------------------------------------------------------
# Engine: ripgrep (preferred) ------------------------------------------------
# ---------------------------------------------------------------------------
HAVE_RG = shutil.which("rg") is not None and not os.environ.get("PFIND_NO_RG")


def _rg_run(cmd, timeout):
    """ripgrep speaks UTF-8; never let the Windows code page decode it (an emoji crashed it)."""
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def rg_list_files(roots, ext_filter, extra_excludes, include_hidden, no_ignore, workers):
    """Enumerate candidate files via `rg --files` (respects .gitignore + our globs)."""
    cmd = ["rg", "--files", "--threads", str(workers)]
    if include_hidden:
        cmd.append("--hidden")
    if no_ignore:
        cmd.append("--no-ignore")
    cmd += rg_common_globs(ext_filter, extra_excludes, include_hidden, no_ignore)
    cmd += [str(r) for r in roots]
    try:
        out = _rg_run(cmd, 120)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"pfind: rg --files failed ({e}); continuing without name search", file=sys.stderr)
        return []
    return [line for line in out.stdout.splitlines() if line]


def rg_content(pattern, roots, regex, ignore_case, ext_filter, extra_excludes,
               include_hidden, no_ignore, workers, max_per_file,
               fixed=None, multiline=False, timeout=600):
    """
    Content search via `rg --json`. Returns {path: {'count','samples','terms'}} where
    'terms' is the set of distinct matched substrings (drives coverage ranking).
      fixed=True  -> literal (-F); fixed=None -> literal unless regex mode.
      multiline=True -> `-U` so a query can span newlines (exact-snippet mode).
    """
    if fixed is None:
        fixed = not regex
    cmd = ["rg", "--json", "--threads", str(workers)]
    if ignore_case:
        cmd.append("-i")
    else:
        cmd.append("-S")  # smart-case: case-insensitive unless query has uppercase
    if fixed:
        cmd.append("-F")  # fixed-string (literal substring)
    if multiline:
        cmd += ["-U", "--multiline-dotall"]
    if include_hidden:
        cmd.append("--hidden")
    if no_ignore:
        cmd.append("--no-ignore")
    cmd += rg_common_globs(ext_filter, extra_excludes, include_hidden, no_ignore)
    cmd += ["-e", pattern, "--"]
    cmd += [str(r) for r in roots]

    try:
        proc = _rg_run(cmd, timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"pfind: rg content search failed: {e}", file=sys.stderr)
        return {}

    hits = defaultdict(lambda: {"count": 0, "samples": [], "terms": set()})
    for line in proc.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "match":
            continue
        d = obj["data"]
        path = d["path"].get("text")
        if path is None:
            continue
        rec = hits[path]
        rec["count"] += 1
        # record which distinct substring matched (coverage signal for ranking)
        for sm in d.get("submatches", []):
            mt = (sm.get("match") or {}).get("text")
            if mt:
                rec["terms"].add(mt.lower()[:40])
        if len(rec["samples"]) < max_per_file:
            rec["samples"].append((d.get("line_number", 0), _sample(d["lines"].get("text") or "")))
    return dict(hits)


def _sample(text):
    """One display line: CRLF-safe, multi-line blocks folded, long lines cut."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if "\n" in text:  # multi-line match block: fold for one-line display
        text = " ↵ ".join(s.strip() for s in text.split("\n") if s.strip())
    text = text.strip()
    return text[:220] + "…" if len(text) > 220 else text


# ---------------------------------------------------------------------------
# Engine: pure-Python fallback (only if rg is missing) -----------------------
# ---------------------------------------------------------------------------
def _norm_exts(ext_filter):
    return {(e if e.startswith(".") else "." + e).lower() for e in (ext_filter or [])}


def _excluded(name, patterns):
    return any(fnmatch.fnmatch(name, g) for g in patterns)


def py_fallback_files(roots, ext_filter, extra_excludes, include_hidden=False):
    """os.walk engine, applying the same rules as the rg globs: every EXCLUDE_GLOBS
    pattern to folder AND file names, hidden entries skipped unless asked, --ext with or
    without its dot. (.gitignore is ripgrep's job; install rg to honour it.)"""
    patterns = list(EXCLUDE_GLOBS) + list(extra_excludes)
    exts = _norm_exts(ext_filter)
    files = []
    for root in roots:
        if Path(root).is_file():
            files.append(str(root))
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if not _excluded(d, patterns) and (include_hidden or not d.startswith("."))]
            for fn in filenames:
                if _excluded(fn, patterns) or (not include_hidden and fn.startswith(".")):
                    continue
                if exts and Path(fn).suffix.lower() not in exts:
                    continue
                files.append(os.path.join(dirpath, fn))
    return files


def _is_binary(fp):
    try:
        with open(fp, "rb") as f:
            return b"\0" in f.read(8192)
    except OSError:
        return True


def py_fallback_content(pattern, files, regex, ignore_case, max_per_file, multiline=False):
    """Pure-Python content search. Same semantics as the rg path: literal unless regex,
    smart-case (insensitive unless the query has a capital, or -i), binaries skipped,
    distinct matched terms recorded for coverage ranking, multi-line patterns matched
    against the whole file."""
    insensitive = ignore_case or pattern == pattern.lower()
    flags = (re.IGNORECASE if insensitive else 0) | (re.DOTALL if multiline else 0)
    rx = re.compile(pattern if regex else re.escape(pattern), flags)
    hits = {}
    for fp in files:
        if _is_binary(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
                text = f.read()
        except OSError:
            continue
        samples, count, terms = [], 0, set()
        if multiline:
            for m in rx.finditer(text):
                count += 1
                terms.add(m.group(0).lower()[:40])
                if len(samples) < max_per_file:
                    lineno = text.count("\n", 0, m.start()) + 1
                    start = text.rfind("\n", 0, m.start()) + 1
                    end = text.find("\n", m.end())
                    samples.append((lineno, _sample(text[start:end if end != -1 else len(text)])))
        else:
            for i, line in enumerate(text.splitlines(), 1):
                found = rx.findall(line)
                if found:
                    count += 1
                    terms.update(str(t).lower()[:40] for t in found if t)
                    if len(samples) < max_per_file:
                        samples.append((i, _sample(line)))
        if count:
            hits[fp] = {"count": count, "samples": samples, "terms": terms}
    return hits


# ---------------------------------------------------------------------------
# Name matching --------------------------------------------------------------
# ---------------------------------------------------------------------------
def _inside(fp, roots):
    """The part of a path below its search root: 'C:\\Users\\me\\Documents' must not
    make every file match a search for 'documents'."""
    for r in roots or ():
        try:
            return str(Path(fp).relative_to(r))
        except ValueError:
            continue
    return fp


def match_names(query, files, regex, ignore_case, fuzzy, roots=None):
    """Rank files by how well the query matches their name/path. Returns [(path, score)].
    Smart-case like the content search: a lowercase query ignores case."""
    scored = []
    insensitive = ignore_case or fuzzy or query == query.lower()
    if regex:
        rx = re.compile(query, re.IGNORECASE if insensitive else 0)
    q = query.lower() if insensitive else query
    for fp in files:
        base = os.path.basename(fp)
        rel = _inside(fp, roots)
        b = base.lower() if insensitive else base
        p = rel.lower() if insensitive else rel
        score = 0.0
        if regex:
            if rx.search(base):
                score = 3.0
            elif rx.search(rel):
                score = 1.5
        else:
            if q == b or q + Path(base).suffix.lower() == b:
                score = 5.0                      # exact basename
            elif q in b:
                score = 3.0                      # substring in name
            elif q in p:
                score = 1.5                      # substring in path
            elif fuzzy:
                r = SequenceMatcher(None, q, b).ratio()
                if r >= 0.6 or _subseq(q, b):
                    score = 0.5 + r              # fuzzy name
        if score > 0:
            scored.append((fp, score))
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored


def _subseq(q, s):
    it = iter(s)
    return all(c in it for c in q)


# ---------------------------------------------------------------------------
# Fusion: Reciprocal Rank Fusion --------------------------------------------
# ---------------------------------------------------------------------------
# A name match is a stronger relevance signal than yet another content hit, and
# semantic recall sits between. Weighted RRF lets a strong name/semantic hit outrank a
# file that merely mentions the term a lot. (Weights are deliberately mild — RRF stays
# scale-invariant; this just tilts ties the right way.)
RRF_WEIGHTS = {"name": 2.0, "semantic": 1.5, "content": 1.0}


def rrf_fuse(rankings, k, weights=RRF_WEIGHTS):
    """
    rankings: dict[label -> ordered list of paths (best first)].
    Returns [(path, fused_score, [labels that contributed])], best first.
    """
    fused = defaultdict(float)
    sources = defaultdict(list)
    for label, ranked in rankings.items():
        w = weights.get(label, 1.0)
        for rank, path in enumerate(ranked, start=1):
            fused[path] += w / (k + rank)
            sources[path].append(label)
    out = [(p, s, sources[p]) for p, s in fused.items()]
    out.sort(key=lambda t: (-t[1], t[0]))
    return out


# ---------------------------------------------------------------------------
# Semantic seam (opt-in, --brain) -------------------------------------------
# ---------------------------------------------------------------------------
def semantic_brain(query, collection, top_k):
    """
    Best-effort semantic query over the Chroma Second Brain. Degrades gracefully:
    on any failure it returns [] and the caller falls back to lexical over the brain.

    The brain was built with embedding model all-MiniLM-L6-v2 (per its own docs), which
    is ALSO Chroma's default embedder — so query_texts works without extra wiring. If the
    collection is ever rebuilt with a different model, pass that model's EmbeddingFunction
    to get_collection() here; until then treat semantic hits as a recall booster.

    Returns a list of dicts: {'id', 'snippet', 'path'} where 'path' is a real filesystem
    path IF the chunk's metadata carries one (then it can fuse with file results), else None.
    """
    try:
        import chromadb
    except ImportError:
        print("pfind: --brain semantic needs chromadb (import failed); using lexical only.",
              file=sys.stderr)
        return []
    if not BRAIN_CHROMA.exists():
        print(f"pfind: brain store not found at {BRAIN_CHROMA}; lexical only.", file=sys.stderr)
        return []
    try:
        client = chromadb.PersistentClient(path=str(BRAIN_CHROMA))
        col = client.get_collection(collection)
        res = col.query(query_texts=[query], n_results=top_k)
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        out = []
        for doc, meta, _id in zip(docs, metas, ids):
            meta = meta or {}
            raw = meta.get("source") or meta.get("path") or meta.get("file")
            path = None
            if raw and Path(str(raw)).expanduser().exists():
                path = str(Path(str(raw)).expanduser().resolve())
            snippet = " ".join((doc or "").split())
            if len(snippet) > 240:
                snippet = snippet[:240] + "…"
            out.append({"id": _id, "snippet": snippet or "(empty chunk)", "path": path})
        return out
    except Exception as e:  # embedding-fn mismatch, missing collection, etc.
        print(f"pfind: semantic query degraded ({type(e).__name__}: {str(e)[:100]}); "
              f"lexical only.", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Rendering ------------------------------------------------------------------
# ---------------------------------------------------------------------------
def c(code, s, use_color):
    return f"\033[{code}m{s}\033[0m" if use_color else s


def setup_console():
    """Never crash on a legacy Windows console, and only colour where colour works.
    Returns True if ANSI colour can be used on stdout."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    if not sys.stdout.isatty():
        return False
    if not IS_WINDOWS:
        return True
    try:  # switch on VT processing (Windows 10+); if refused, no colour
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except (OSError, AttributeError):
        return False


def render_json(fused, content_hits, limit):
    """Machine-readable results for agents: one object, ranked, no colour, no prose."""
    out = []
    for path, score, labels in fused[: limit or None]:
        h = content_hits.get(path, {})
        out.append({"path": path, "score": round(score, 5), "why": labels,
                    "hits": h.get("count", 0),
                    "samples": [{"line": n, "text": t} for n, t in h.get("samples", [])]})
    print(json.dumps({"engine": "ripgrep" if HAVE_RG else "python", "matched": len(fused),
                      "results": out}, ensure_ascii=False, indent=1))


def render(fused, name_scores, content_hits, args, use_color):
    if not fused:
        print("no matches.", file=sys.stderr)
        return 0
    shown = 0
    for path, score, labels in fused:
        if args.limit and shown >= args.limit:
            break
        shown += 1
        why = []
        if "name" in labels:
            why.append(c("36", "name", use_color))
        if "content" in labels:
            n = content_hits.get(path, {}).get("count", 0)
            why.append(c("33", f"{n} hit{'s' if n != 1 else ''}", use_color))
        if "semantic" in labels:
            why.append(c("35", "semantic", use_color))
        tag = ",".join(why)
        header = f"{c('90', f'{score:6.4f}', use_color)}  [{tag}]  {c('1;32', path, use_color)}"
        if args.files_only:
            print(path)
            continue
        print(header)
        if not args.names:  # show content samples unless name-only mode
            for lineno, text in content_hits.get(path, {}).get("samples", []):
                print(f"    {c('90', f'{lineno}:', use_color)} {text}")
    if args.count:
        print(f"\n--- {len(fused)} file(s) matched"
              + (f", showing {shown}" if args.limit and len(fused) > shown else "")
              + " ---", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Snippet mode ---------------------------------------------------------------
# ---------------------------------------------------------------------------
def build_loose_regex(snippet):
    """
    Turn a remembered code block into a whitespace-tolerant multi-line regex:
    escape every regex metachar, then collapse each run of whitespace to \\s+ so the
    match survives reindentation / tabs-vs-spaces / reflowed blank lines. This is the
    'I only half-remember how it was formatted' path.
    """
    parts = [re.escape(tok) for tok in snippet.split()]
    return r"\s+".join(p for p in parts if p)


def build_exact_regex(snippet):
    """An exact multi-line snippet that also matches Windows (CRLF) files: literal text,
    with every line break in the snippet allowed to be \\n or \\r\\n in the file."""
    lines = snippet.replace("\r\n", "\n").split("\n")
    return r"\r?\n".join(re.escape(line) for line in lines)


# ---------------------------------------------------------------------------
# Main -----------------------------------------------------------------------
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Doctor: what this computer has, what pfind needs, how to get it ------------
# ---------------------------------------------------------------------------
def _version(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def rg_install_options():
    """Install commands for ripgrep that will work on THIS machine, best first."""
    opts = []
    if IS_WINDOWS:
        if shutil.which("winget"):
            opts.append(["winget", "install", "-e", "--id", "BurntSushi.ripgrep.MSVC",
                         "--accept-package-agreements", "--accept-source-agreements"])
        if shutil.which("scoop"):
            opts.append(["scoop", "install", "ripgrep"])
        if shutil.which("choco"):
            opts.append(["choco", "install", "ripgrep", "-y"])
    else:
        for tool, cmd in (("apt-get", ["sudo", "apt-get", "install", "-y", "ripgrep"]),
                          ("dnf", ["sudo", "dnf", "install", "-y", "ripgrep"]),
                          ("pacman", ["sudo", "pacman", "-S", "--noconfirm", "ripgrep"]),
                          ("zypper", ["sudo", "zypper", "install", "-y", "ripgrep"]),
                          ("brew", ["brew", "install", "ripgrep"])):
            if shutil.which(tool):
                opts.append(cmd)
    return opts


def doctor(as_json=False, ask=True):
    """Scan the computer, say plainly what is there and what is missing, and OFFER to
    install ripgrep. Nothing is installed without the person typing 'y'."""
    rg = shutil.which("rg")
    checks = [
        ("Python", True, f"{sys.version.split()[0]} at {sys.executable}", ""),
        ("ripgrep (rg)", bool(rg), (_version(["rg", "--version"]) or "found") + f" at {rg}" if rg else "not installed",
         "" if rg else "pfind works without it, but slowly and without .gitignore rules."),
        ("Console text", True, f"stdout encoding {sys.stdout.encoding}",
         "pfind switches its own output to UTF-8, so any file content is safe to print."),
        ("Presets file", _preset_file().is_file(), str(_preset_file()),
         "" if _preset_file().is_file() else "optional: map --brain/--work/--src to your own folders."),
    ]
    if IS_WINDOWS and shutil.which("py"):
        broken = _version(["py", "-3", "-c", "print('ok')"]) != "ok"
        checks.append(("py launcher", not broken, "works" if not broken else "installed but cannot start Python",
                       "" if not broken else "it points at a Python that was removed (often an old user account). "
                                             "pfind.cmd falls back to 'python'; to repair: reinstall Python."))
    import importlib.util
    if importlib.util.find_spec("chromadb"):
        checks.append(("Semantic search (--brain)", True, "chromadb installed", ""))
    else:
        checks.append(("Semantic search (--brain)", False, "chromadb not installed",
                       "optional: only for --brain. pip install chromadb"))
    options = [] if rg else rg_install_options()
    if as_json:
        print(json.dumps({"checks": [{"name": n, "ok": ok, "detail": d, "advice": a} for n, ok, d, a in checks],
                          "install_ripgrep": [" ".join(o) for o in options]}, indent=1))
        return 0
    print(f"pfind doctor - {'Windows' if IS_WINDOWS else sys.platform}\n")
    for name, ok, detail, advice in checks:
        print(f"  [{'ok' if ok else '--'}] {name:<26} {detail}")
        if advice:
            print(f"       {advice}")
    if rg:
        print("\nEverything pfind needs is here.")
        return 0
    print("\nTo install ripgrep:")
    if not options:
        print("  No package manager found. Download rg from https://github.com/BurntSushi/ripgrep/releases,"
              "\n  unzip it, and put rg" + (".exe" if IS_WINDOWS else "") + " in a folder on your PATH.")
        return 0
    for i, o in enumerate(options, 1):
        print(f"  {i}. {' '.join(o)}")
    if not (ask and sys.stdin.isatty()):
        print("\nRun one of the commands above, then run pfind --doctor again.")
        return 0
    try:
        answer = input(f"\nInstall ripgrep now with option 1 ({options[0][0]})? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):   # no keyboard after all (Git Bash reports a tty): that is a no
        answer = ""
        print()
    if answer != "y":
        print("Nothing installed.")
        return 0
    r = subprocess.run(options[0])
    ok = r.returncode == 0 and (shutil.which("rg") or _version(["rg", "--version"]))
    print("ripgrep installed. Open a new terminal so PATH picks it up." if ok
          else f"The installer exited with {r.returncode}; try another option above.")
    return 0 if ok else 1


def build_parser():
    p = argparse.ArgumentParser(
        prog="pfind",
        description="Hybrid ranked search (name+content+fuzzy, RRF-fused). Windows and Linux.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="presets: --brain --work --src --all   (see file header for examples)\n"
               "first time here? run:  pfind --doctor")
    p.add_argument("query", nargs="?", help="what to find (literal substring by default; regex with -r); "
                                            "'-' reads it from stdin")
    p.add_argument("--query-file", metavar="FILE", help="read the query (e.g. a multi-line snippet) from FILE")
    p.add_argument("--doctor", action="store_true",
                   help="check this computer, say what is missing, offer to install ripgrep")
    p.add_argument("--json", action="store_true", help="machine-readable results (for agents)")
    p.add_argument("paths", nargs="*", help="roots to search (default: cwd, or a preset)")
    # presets
    p.add_argument("--brain", action="store_true", help="search ~/Documents/SECOND.BRAIN + enable semantic seam")
    p.add_argument("--work", action="store_true", help="search ~/Documents/FIREFOX.WORK")
    p.add_argument("--src", action="store_true", help="search ~/firefox-main")
    p.add_argument("--all", action="store_true", help="search brain + work + src")
    # what to match
    p.add_argument("--names", action="store_true", help="filenames only")
    p.add_argument("--content", action="store_true", help="file contents only")
    p.add_argument("-r", "--regex", action="store_true", help="treat query as a regex")
    p.add_argument("-i", "--ignore-case", action="store_true", help="force case-insensitive")
    p.add_argument("--fuzzy", action="store_true", help="typo/partial-tolerant name matching")
    p.add_argument("-x", "--exact", action="store_true",
                   help="exact multi-line snippet: literal match, spans newlines (paste code as-is)")
    p.add_argument("--loose", action="store_true",
                   help="snippet match tolerant of whitespace/indent drift (implies multi-line)")
    # scope
    p.add_argument("--ext", nargs="+", metavar="EXT", help="only these extensions (.py .sh ...)")
    p.add_argument("--exclude", nargs="+", metavar="GLOB", default=[], help="extra excludes")
    p.add_argument("--hidden", action="store_true", help="include hidden files")
    p.add_argument("--no-ignore", action="store_true", help="ignore .gitignore rules")
    # tuning / output
    p.add_argument("--workers", type=int, default=LOGICAL_CPUS, help=f"rg threads (default {LOGICAL_CPUS})")
    p.add_argument("--timeout", type=int, default=600, help="content-search timeout seconds (default 600)")
    p.add_argument("--rrf-k", type=int, default=RRF_K_DEFAULT, help=f"RRF k (default {RRF_K_DEFAULT}; lower sharpens small corpora)")
    p.add_argument("--max", type=int, default=5, help="content samples shown per file (default 5)")
    p.add_argument("--limit", type=int, default=40, help="max files shown (default 40; 0 = all)")
    p.add_argument("-C", "--context", type=int, default=0, help="(reserved) context lines")
    p.add_argument("--collection", default=BRAIN_DEFAULT_COLLECTION, help="brain collection for semantic")
    p.add_argument("--files-only", action="store_true", help="print paths only")
    p.add_argument("--count", action="store_true", help="print match count summary")
    p.add_argument("--no-color", action="store_true", help="disable ANSI color")
    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    use_color = setup_console() and not args.no_color and not args.json

    if args.doctor:
        return doctor(as_json=args.json)
    if args.query_file:
        args.query = Path(args.query_file).read_text(encoding="utf-8", errors="replace")
    elif args.query == "-":
        args.query = sys.stdin.read()
    if args.query is None:
        parser.error("a query is needed (or --query-file FILE, or '-' for stdin, or --doctor)")
    args.query = args.query.replace("\r\n", "\n")
    if args.query.endswith("\n") and args.query.count("\n") > 1:
        args.query = args.query.rstrip("\n")          # a pasted file ends with a newline

    presets = [name for name in ("brain", "work", "src") if getattr(args, name)]
    if args.all:
        presets = ["brain", "work", "src"]
    roots = resolve_roots(args.paths, presets)

    # snippet mode: an exact/loose flag, or a query that already spans newlines.
    snippet_mode = args.exact or args.loose or ("\n" in args.query)
    # a pasted code block is never a filename → content-only in snippet mode.
    do_names = (not args.content) and not snippet_mode
    do_content = not args.names or snippet_mode

    # resolve the content pattern + engine flags for this mode
    if args.loose:
        pattern, use_regex, use_fixed, multiline = build_loose_regex(args.query), True, False, True
    elif snippet_mode:                     # --exact or a multi-line paste → literal, spanning newlines,
        # as a regex so each line break matches both \n and \r\n (Windows files)
        pattern, use_regex, use_fixed, multiline = build_exact_regex(args.query), True, False, True
    else:
        pattern, use_regex, use_fixed, multiline = args.query, args.regex, not args.regex, False

    # 1. enumerate + score names
    name_ranked, name_scores = [], {}
    if do_names:
        files = (rg_list_files(roots, args.ext, args.exclude, args.hidden, args.no_ignore, args.workers)
                 if HAVE_RG else py_fallback_files(roots, args.ext, args.exclude, args.hidden))
        scored = match_names(args.query, files, args.regex, args.ignore_case, args.fuzzy, roots)
        name_ranked = [fp for fp, _ in scored]
        name_scores = dict(scored)

    # 2. content search
    content_hits = {}
    if do_content:
        if HAVE_RG:
            content_hits = rg_content(pattern, roots, use_regex, args.ignore_case,
                                      args.ext, args.exclude, args.hidden, args.no_ignore,
                                      args.workers, args.max,
                                      fixed=use_fixed, multiline=multiline, timeout=args.timeout)
        else:
            files = py_fallback_files(roots, args.ext, args.exclude, args.hidden)
            content_hits = py_fallback_content(pattern, files, use_regex, args.ignore_case, args.max,
                                               multiline=multiline)
    # RANK BY COVERAGE, not volume: files that match the most DISTINCT query-terms rank
    # first (a config matching regdom+channel14+unlock beats a source file that says
    # 'all channels' 200x). Raw hit-count is only the tiebreak.
    content_ranked = [p for p, _ in sorted(
        content_hits.items(),
        key=lambda kv: (-len(kv[1].get("terms", ())), -kv[1]["count"], kv[0]))]

    # 3. optional semantic (brain only). Chunks WITH a real path fuse into the file
    #    ranking; pathless memory chunks are shown separately as "brain recall".
    semantic_ranked, brain_recall = [], []
    if args.brain:
        for hit in semantic_brain(args.query, args.collection, top_k=max(args.max, 5)):
            if hit["path"]:
                if hit["path"] not in semantic_ranked:
                    semantic_ranked.append(hit["path"])
            else:
                brain_recall.append(hit)

    # 4. fuse
    rankings = {}
    if name_ranked:
        rankings["name"] = name_ranked
    if content_ranked:
        rankings["content"] = content_ranked
    if semantic_ranked:
        rankings["semantic"] = semantic_ranked

    if not rankings and not brain_recall:
        if args.json:
            render_json([], {}, 0)
        else:
            print("no matches.", file=sys.stderr)
        return 1

    if not HAVE_RG and not args.json:
        print("pfind: ripgrep not found - using the slower built-in engine. "
              "Run  pfind --doctor  to install it.", file=sys.stderr)

    fused = rrf_fuse(rankings, args.rrf_k) if rankings else []
    if args.json:
        render_json(fused, content_hits, args.limit)
        return 0
    render(fused, name_scores, content_hits, args, use_color)

    # pathless brain memory chunks: shown separately, they aren't files
    if brain_recall and not args.files_only:
        print(f"\n{c('35', '🧠 brain recall (semantic — memory chunks, not files):', use_color)}")
        for hit in brain_recall:
            print(f"    {c('90', '·', use_color)} {hit['snippet']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
