#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# pfind — Unified hybrid local search, content extraction, and filesystem exploration.
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
# VERSION: 3.0.0 | UPDATED: 2026-08-15 | STATUS: live
# CHANGELOG:
#   3.0.0 (2026-08-15) — The Super-Merge: unified ripgrep-15.2.0 + eza-0.23.5 capabilities into pfind.
#       (1) RIPGREP INGESTION: Context lines (-C, -A, -B) with line-range deduplication & '--' markers;
#           archive/compressed search (-z/--search-zip for .gz, .bz2, .xz, .lzma, .zst, .tar, .zip);
#           50+ language type definitions (-t/--type, -T/--type-not); binary NUL-byte heuristic skipping;
#           invert-match (-v), only-matching (-o), regex replacement preview (-r/--replace), count (-c),
#           and search performance statistics (--stats).
#       (2) EZA INGESTION: Comment-aware syntax & LOC counting (--loc, --code) across 50+ languages;
#           Git working-tree status flags ([M], [A], [?], [D], [U], [I]) + --git-dirty filter & boost;
#           Hierarchical tree view (-T/--tree, --level); relative timestamps (--time-style=relative,iso);
#           extended metadata (-l/--long, --octal-permissions, --blocks, --inode, --links, --binary-units);
#           OSC 8 clickable terminal hyperlinks (--hyperlink); Nerd Font icons (--icons); adaptive color scales.
#       (3) EXPLORATORY MODE: Running without a query switches to smart directory/tree/metadata listing.
#       (4) BASELINE PRESERVATION: 100% backward-compatible with 2.x hybrid RRF ranking, coverage scoring,
#           exact/loose snippet search (-x, --loose), architecture presets (--brain/--work/--src/--all),
#           Chroma Second Brain semantic seam, and zero-dependency pure-Python fallback.
#   2.1.0 (2026-07-22) — Needle-in-a-haystack-of-needles upgrade. Exact multi-line snippet search (-x/--loose).
#   2.0.0 (2026-07-22) — Full rewrite. Hybrid search: filename + content + fuzzy, fused with RRF.
#   1.0.0 — original parallel mmap+re grep.
"""
pfind — find stuff, analyze code, and explore filesystems in one shot.

Combines:
  1. ripgrep 15.2.0: SIMD/mmap regex, context windowing, archive decomp, language types, binary heuristics.
  2. eza 0.23.5: Git status badges, syntax-aware LOC lexer, visual trees, relative times, hyperlinks, icons.
  3. pfind 2.1.0: Hybrid RRF fusion, term coverage ranking, snippet matching, Chroma Second Brain semantic seam.
"""

import argparse
import bz2
import datetime
import fnmatch
import gzip
import json
import lzma
import math
import os
import pwd
import grp
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Machine & Architecture Constants
# ---------------------------------------------------------------------------
MACHINE = "gorilla-sve14a3aj"
LOGICAL_CPUS = 8

HOME = Path.home()
PRESET_ROOTS = {
    "brain": HOME / "Documents" / "SECOND.BRAIN",
    "work":  HOME / "Documents" / "FIREFOX.WORK",
    "src":   HOME / "firefox-main",
}
BRAIN_CHROMA = HOME / "Documents" / "SECOND.BRAIN" / "Chroma.DB.and.Brain.xml" / "chroma_db"
BRAIN_DEFAULT_COLLECTION = "core_memory"

EXCLUDE_GLOBS = [
    ".git", ".hg", ".svn", "node_modules", "__pycache__",
    ".mozbuild", "venv", ".venv", "vector_env", "dist", "build",
    "obj-*",
    "chroma_db", "chroma_fx154",
    "*.sqlite3", "*.bin", "*.parquet", "*.pyc",
    "*.min.js", "*.map",
]

RRF_K_DEFAULT = 60
RRF_WEIGHTS_DEFAULT = {
    "name": 2.0,
    "semantic": 1.5,
    "content": 1.0,
    "git": 0.8,
    "recency": 0.5,
}

HAVE_RG = shutil.which("rg") is not None
HAVE_GIT = shutil.which("git") is not None

# ---------------------------------------------------------------------------
# Language Type Definitions (from ripgrep-15.2.0 crates/ignore/src/default_types.rs)
# ---------------------------------------------------------------------------
LANGUAGE_TYPES = {
    "c": [".c", ".h"],
    "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h", ".C", ".H"],
    "rust": [".rs"],
    "python": [".py", ".pyi", ".pyx"],
    "py": [".py", ".pyi", ".pyx"],
    "go": [".go"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "js": [".js", ".jsx", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx", ".mts", ".cts"],
    "ts": [".ts", ".tsx", ".mts", ".cts"],
    "html": [".html", ".htm", ".xhtml"],
    "css": [".css", ".scss", ".sass", ".less"],
    "json": [".json", ".jsonc", ".jsonl"],
    "yaml": [".yaml", ".yml"],
    "toml": [".toml"],
    "markdown": [".md", ".markdown", ".mdown", ".mkdn"],
    "md": [".md", ".markdown"],
    "sh": [".sh", ".bash", ".zsh", ".ksh"],
    "bash": [".sh", ".bash", ".zsh"],
    "java": [".java", ".jsp"],
    "kotlin": [".kt", ".kts"],
    "swift": [".swift"],
    "ruby": [".rb", ".rake", ".gemspec"],
    "php": [".php", ".phtml", ".php3", ".php4", ".php5"],
    "perl": [".pl", ".pm", ".t"],
    "lua": [".lua"],
    "zig": [".zig"],
    "nim": [".nim", ".nims"],
    "scala": [".scala", ".sc"],
    "sql": [".sql"],
    "xml": [".xml", ".xsl", ".xslt", ".svg", ".plist"],
    "docker": ["Dockerfile", ".dockerignore"],
    "make": ["Makefile", "makefile", ".mk", ".mak"],
    "cmake": ["CMakeLists.txt", ".cmake"],
    "assembly": [".s", ".S", ".asm"],
    "asm": [".s", ".S", ".asm"],
}

# ---------------------------------------------------------------------------
# Comment Syntax Lexer Definitions (from eza-0.23.5 src/loc/mod.rs)
# ---------------------------------------------------------------------------
class LanguageSyntax:
    def __init__(self, name, line_comments, block_comments, extensions, filenames=None):
        self.name = name
        self.line_comments = line_comments
        self.block_comments = block_comments  # list of (open, close)
        self.extensions = set(extensions)
        self.filenames = set(filenames or [])

SYNTAX_TABLE = [
    LanguageSyntax("C/C++", ["//"], [("/*", "*/")], [".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".C", ".H"]),
    LanguageSyntax("Rust", ["//"], [("/*", "*/")], [".rs"]),
    LanguageSyntax("Python", ["#"], [('"""', '"""'), ("'''", "'''")], [".py", ".pyi", ".pyx", ".pyw"]),
    LanguageSyntax("Go", ["//"], [("/*", "*/")], [".go"]),
    LanguageSyntax("JavaScript/TypeScript", ["//"], [("/*", "*/")], [".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"]),
    LanguageSyntax("Shell", ["#"], [], [".sh", ".bash", ".zsh", ".ksh", ".ebuild", ".eclass"]),
    LanguageSyntax("HTML/XML", [], [("<!--", "-->")], [".html", ".htm", ".xhtml", ".xml", ".svg", ".plist"]),
    LanguageSyntax("CSS", ["//"], [("/*", "*/")], [".css", ".scss", ".sass", ".less"]),
    LanguageSyntax("JSON", ["//"], [("/*", "*/")], [".json", ".jsonc"]),
    LanguageSyntax("YAML/TOML", ["#"], [], [".yaml", ".yml", ".toml"]),
    LanguageSyntax("Markdown", [], [("<!--", "-->")], [".md", ".markdown"]),
    LanguageSyntax("Java/Kotlin", ["//"], [("/*", "*/")], [".java", ".kt", ".kts"]),
    LanguageSyntax("Swift", ["//"], [("/*", "*/")], [".swift"]),
    LanguageSyntax("Ruby", ["#"], [("=begin", "=end")], [".rb", ".rake", ".gemspec"]),
    LanguageSyntax("PHP", ["//", "#"], [("/*", "*/")], [".php", ".phtml"]),
    LanguageSyntax("Perl", ["#"], [("=pod", "=cut")], [".pl", ".pm", ".t"]),
    LanguageSyntax("Lua", ["--"], [("--[[", "]]")], [".lua"]),
    LanguageSyntax("Zig", ["//"], [], [".zig"]),
    LanguageSyntax("Nim", ["#"], [("#[", "]#")], [".nim", ".nims"]),
    LanguageSyntax("SQL", ["--"], [("/*", "*/")], [".sql"]),
    LanguageSyntax("Makefile", ["#"], [], [".mk", ".mak"], ["Makefile", "makefile", "GNUmakefile"]),
    LanguageSyntax("CMake", ["#"], [("#[[", "]]")], [".cmake"], ["CMakeLists.txt"]),
    LanguageSyntax("Assembly", [";", "//", "#", "@"], [("/*", "*/")], [".s", ".S", ".asm"]),
]

EXT_TO_SYNTAX = {}
FILE_TO_SYNTAX = {}
for syn in SYNTAX_TABLE:
    for ext in syn.extensions:
        EXT_TO_SYNTAX[ext.lower()] = syn
    for fn in syn.filenames:
        FILE_TO_SYNTAX[fn.lower()] = syn

# ---------------------------------------------------------------------------
# Nerd Font Icons Map (from eza-0.23.5 src/output/icons.rs)
# ---------------------------------------------------------------------------
NERD_ICONS = {
    # File extensions
    ".rs": "\ue68b", ".py": "\ue606", ".c": "\ue61e", ".h": "\ue61e",
    ".cpp": "\ue61d", ".hpp": "\ue61d", ".go": "\ue627", ".js": "\ue74e",
    ".ts": "\ue628", ".tsx": "\ue7ba", ".jsx": "\ue7ba", ".html": "\ue736",
    ".css": "\ue749", ".scss": "\ue749", ".json": "\ue60b", ".yaml": "\ue6a8",
    ".yml": "\ue6a8", ".toml": "\ue6b2", ".md": "\ue609", ".sh": "\ue795",
    ".bash": "\ue795", ".zsh": "\ue795", ".java": "\ue738", ".kt": "\ue634",
    ".swift": "\ue755", ".rb": "\ue739", ".php": "\ue73d", ".lua": "\ue620",
    ".zig": "\ue6a9", ".nim": "\ue677", ".sql": "\ue706", ".xml": "\ue796",
    ".tar": "\uf410", ".gz": "\uf410", ".zip": "\uf410", ".xz": "\uf410",
    ".zst": "\uf410", ".png": "\uf1c5", ".jpg": "\uf1c5", ".jpeg": "\uf1c5",
    ".svg": "\uf1c5", ".pdf": "\uf1c1", ".deb": "\ue77d", ".lock": "\uf023",
    # Special filenames
    "makefile": "\ue660", "cmakelists.txt": "\ue660", "dockerfile": "\ue650",
    "license": "\uf02d", "readme.md": "\uf02d", ".gitignore": "\ue725",
    # Default fallbacks
    "dir": "\ue5ff", "file": "\uf15b", "symlink": "\uf0c1", "binary": "\ueae8",
}

# ---------------------------------------------------------------------------
# Helper: ANSI Colors & Formatting
# ---------------------------------------------------------------------------
def c(code, s, use_color):
    return f"\033[{code}m{s}\033[0m" if use_color else s

def make_hyperlink(path, line=0, display_text=None, use_hyperlink=False, format_type="file"):
    text = display_text or path
    if not use_hyperlink:
        return text
    
    abs_path = os.path.abspath(path)
    
    if format_type == "vscode":
        # VSCode format: vscode://file/path:line
        target = f"vscode://file{abs_path}"
        if line > 0:
            target += f":{line}"
    elif format_type == "grep+":
        # grep+ format: file://path with #L line anchor
        target = f"file://{abs_path}"
        if line > 0:
            target += f"#L{line}"
    else:  # file format (default)
        target = f"file://{MACHINE}{abs_path}"
        if line > 0:
            target += f"#{line}"
    
    return f"\033]8;;{target}\033\\{text}\033]8;;\033\\"

# ---------------------------------------------------------------------------
# Root & Scope Resolution
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
    seen, out = set(), []
    for r in roots:
        rs = str(r)
        if rs not in seen:
            seen.add(rs)
            out.append(r)
    return out

def resolve_type_globs(types, types_not):
    globs = []
    if types:
        for t in types:
            t_lower = t.lower()
            if t_lower in LANGUAGE_TYPES:
                for ext in LANGUAGE_TYPES[t_lower]:
                    globs.append(f"*{ext}")
            else:
                globs.append(f"*.{t}" if not t.startswith(".") else f"*{t}")
    if types_not:
        for t in types_not:
            t_lower = t.lower()
            if t_lower in LANGUAGE_TYPES:
                for ext in LANGUAGE_TYPES[t_lower]:
                    globs.append(f"!*{ext}")
            else:
                globs.append(f"!*.{t}" if not t.startswith(".") else f"!*{t}")
    return globs

def rg_common_globs(ext_filter, extra_excludes, type_globs, globs=()):
    """Build ripgrep -g override globs. ``globs`` are user-supplied include
    globs (e.g. ``*.md``) or excludes prefixed with ``!``. When only includes
    are given, ripgrep's override semantics make every other path ignored,
    matching ripgrep-15.2.0/crates/ignore/src/overrides.rs behaviour."""
    out = []
    for g in EXCLUDE_GLOBS:
        out += ["-g", f"!{g}"]
    for g in extra_excludes:
        out += ["-g", f"!{g}"]
    if ext_filter:
        for e in ext_filter:
            e = e if e.startswith(".") else "." + e
            out += ["-g", f"*{e}"]
    for tg in type_globs:
        out += ["-g", tg]
    for g in globs:
        out += ["-g", g]
    return out


def _apply_user_globs(paths, globs, is_dir=False):
    """Filter ``paths`` by user-supplied ``-g`` globs using ripgrep override
    semantics (see ripgrep-15.2.0 crates/ignore/src/overrides.rs): a leading
    ``!`` turns a glob into a re-include (whitelist); when at least one plain
    include glob is present, every path that matches none of the includes is
    ignored. This is the pure-Python mirror used when ripgrep is unavailable;
    the rg path hands the same ``-g`` args straight to ripgrep.
    """
    if not globs:
        return paths
    includes = [g for g in globs if not g.startswith("!")]
    excludes = [g[1:] for g in globs if g.startswith("!")]

    def gmatch(path, pattern):
        # Match on the basename for patterns that do not contain a slash
        # (ripgrep matches *-only globs against the basename), else the full
        # path, which is how globset behaves.
        if "/" not in pattern:
            return (fnmatch.fnmatch(os.path.basename(path), pattern)
                    or fnmatch.fnmatch(path, pattern))
        return fnmatch.fnmatch(path, pattern)

    filtered = []
    for p in paths:
        if any(gmatch(p, e) for e in excludes):
            continue
        if includes and not any(gmatch(p, g) for g in includes):
            continue
        filtered.append(p)
    return filtered

# ---------------------------------------------------------------------------
# Comment-Aware LOC Classifier (from eza-0.23.5 src/loc/mod.rs)
# ---------------------------------------------------------------------------
class LocCounts:
    __slots__ = ("lines", "code", "comments", "blanks")
    def __init__(self, lines=0, code=0, comments=0, blanks=0):
        self.lines = lines
        self.code = code
        self.comments = comments
        self.blanks = blanks

    def add(self, other):
        self.lines += other.lines
        self.code += other.code
        self.comments += other.comments
        self.blanks += other.blanks

def classify_file_loc(path):
    fn = os.path.basename(path).lower()
    ext = os.path.splitext(fn)[1].lower()
    syntax = FILE_TO_SYNTAX.get(fn) or EXT_TO_SYNTAX.get(ext)
    if not syntax:
        return None

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except (OSError, UnicodeError):
        return None

    counts = LocCounts(lines=len(lines))
    active_block_closer = None

    for line in lines:
        rest = line.strip()
        if not rest:
            counts.blanks += 1
            continue

        has_code = False
        has_comment = False

        while rest:
            if active_block_closer:
                has_comment = True
                idx = rest.find(active_block_closer)
                if idx != -1:
                    rest = rest[idx + len(active_block_closer):].strip()
                    active_block_closer = None
                    continue
                else:
                    rest = ""
                    break

            if not rest:
                break

            # check line comments
            is_line_comment = False
            for lc in syntax.line_comments:
                if rest.startswith(lc):
                    has_comment = True
                    is_line_comment = True
                    rest = ""
                    break
            if is_line_comment:
                break

            # check block comment openers
            found_block = False
            for b_open, b_close in syntax.block_comments:
                if rest.startswith(b_open):
                    has_comment = True
                    active_block_closer = b_close
                    rest = rest[len(b_open):].strip()
                    found_block = True
                    break
            if found_block:
                continue

            # otherwise character is code
            has_code = True
            rest = rest[1:].strip()

        if has_code:
            counts.code += 1
        elif has_comment:
            counts.comments += 1
        else:
            counts.blanks += 1

    return syntax.name, counts

# ---------------------------------------------------------------------------
# Git Status Engine (from eza-0.23.5 src/fs/feature/git.rs)
# ---------------------------------------------------------------------------
class GitStatusCache:
    def __init__(self, roots):
        self.status_map = {}  # abs_path -> status_str ("M", "A", "?", "U", "D")
        if not HAVE_GIT:
            return
        repo_roots = set()
        for r in roots:
            try:
                out = subprocess.run(
                    ["git", "-C", str(r), "rev-parse", "--show-toplevel"],
                    capture_output=True, text=True, timeout=5
                )
                if out.returncode == 0 and out.stdout.strip():
                    repo_roots.add(out.stdout.strip())
            except Exception:
                pass

        for repo in repo_roots:
            try:
                proc = subprocess.run(
                    ["git", "-C", repo, "status", "--porcelain=v1", "-z", "-uall"],
                    capture_output=True, text=True, timeout=10
                )
                if proc.returncode == 0:
                    raw_entries = proc.stdout.split("\0")
                    for entry in raw_entries:
                        if len(entry) >= 4:
                            st = entry[:2].strip()
                            rel_path = entry[3:]
                            abs_p = str(Path(repo) / rel_path)
                            self.status_map[abs_p] = st
            except Exception:
                pass

    def get_status(self, path):
        return self.status_map.get(os.path.abspath(path))

# ---------------------------------------------------------------------------
# Filesystem Metadata & Formatting Engine (from eza-0.23.5 src/output/)
# ---------------------------------------------------------------------------
def format_size(size_bytes, binary_units=True):
    if size_bytes is None:
        return "     -"
    base = 1024.0 if binary_units else 1000.0
    suffixes = ["B", "KiB", "MiB", "GiB", "TiB"] if binary_units else ["B", "KB", "MB", "GB", "TB"]
    val = float(size_bytes)
    for s in suffixes:
        if val < base or s == suffixes[-1]:
            if s == "B":
                return f"{int(val):>5d} B"
            return f"{val:>5.1f} {s}"
        val /= base
    return f"{val:.1f} B"

def format_permissions(mode, octal=False):
    if octal:
        return f"{stat.S_IMODE(mode):04o}"
    is_dir = "d" if stat.S_ISDIR(mode) else "-"
    flags = [
        "r" if mode & stat.S_IRUSR else "-",
        "w" if mode & stat.S_IWUSR else "-",
        "x" if mode & stat.S_IXUSR else "-",
        "r" if mode & stat.S_IRGRP else "-",
        "w" if mode & stat.S_IWGRP else "-",
        "x" if mode & stat.S_IXGRP else "-",
        "r" if mode & stat.S_IROTH else "-",
        "w" if mode & stat.S_IWOTH else "-",
        "x" if mode & stat.S_IXOTH else "-",
    ]
    return is_dir + "".join(flags)

def format_timestamp(ts, style="relative"):
    dt = datetime.datetime.fromtimestamp(ts)
    if style == "iso":
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now()
    delta = now - dt
    secs = delta.total_seconds()
    if secs < 0:
        return dt.strftime("%Y-%m-%d")
    if secs < 60:
        return f"{int(secs)}s ago"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    if secs < 86400 * 30:
        return f"{int(secs // 86400)}d ago"
    if secs < 86400 * 365:
        return f"{int(secs // (86400 * 30))}mo ago"
    return f"{int(secs // (86400 * 365))}y ago"

def get_file_icon(path, is_dir=False):
    if is_dir:
        return NERD_ICONS["dir"]
    fn = os.path.basename(path).lower()
    if fn in NERD_ICONS:
        return NERD_ICONS[fn]
    ext = os.path.splitext(fn)[1].lower()
    return NERD_ICONS.get(ext, NERD_ICONS["file"])

def is_binary_file(path, sample_size=8192):
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
            return b"\x00" in chunk
    except OSError:
        return False

# ---------------------------------------------------------------------------
# Search Engine: ripgrep 15.2.0 Ingestion with Context Windowing
# ---------------------------------------------------------------------------
def rg_list_files(roots, ext_filter, extra_excludes, type_globs, include_hidden, no_ignore, workers, max_depth=None, globs=()):
    cmd = ["rg", "--files", "--threads", str(workers)]
    if include_hidden:
        cmd.append("--hidden")
    if no_ignore:
        cmd.append("--no-ignore")
    if max_depth:
        cmd += ["--max-depth", str(max_depth)]
    cmd += rg_common_globs(ext_filter, extra_excludes, type_globs, globs)
    cmd += [str(r) for r in roots]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"pfind: rg --files failed ({e}); fallback enumeration", file=sys.stderr)
        return []
    return [line for line in out.stdout.splitlines() if line]

def rg_content(pattern, roots, regex, ignore_case, case_sensitive, word_regexp,
               ext_filter, extra_excludes, type_globs, include_hidden, no_ignore,
               workers, max_per_file, fixed=None, multiline=False, search_zip=False,
               context_before=0, context_after=0, max_depth=None, pcre2=False,
               invert_match=False, timeout=600, extract_column=False,
               pre=None, pre_glob=None, globs=()):
    if fixed is None:
        fixed = not regex
    cmd = ["rg", "--json", "--threads", str(workers)]
    if case_sensitive:
        cmd.append("-s")
    elif ignore_case:
        cmd.append("-i")
    else:
        cmd.append("-S")
    if fixed:
        cmd.append("-F")
    if word_regexp:
        cmd.append("-w")
    if multiline:
        cmd += ["-U", "--multiline-dotall"]
    if search_zip:
        cmd.append("-z")
    if pcre2:
        cmd.append("--pcre2")
    if invert_match:
        cmd.append("-v")
    if include_hidden:
        cmd.append("--hidden")
    if no_ignore:
        cmd.append("--no-ignore")
    if max_depth:
        cmd += ["--max-depth", str(max_depth)]
    if context_before > 0:
        cmd += ["-B", str(context_before)]
    if context_after > 0:
        cmd += ["-A", str(context_after)]
    if extract_column:
        cmd.append("--column")
    if pre:
        cmd += ["--pre", pre]
    if pre_glob:
        cmd += ["--pre-glob", pre_glob]

    cmd += rg_common_globs(ext_filter, extra_excludes, type_globs, globs)
    cmd += ["-e", pattern, "--"]
    cmd += [str(r) for r in roots]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"pfind: rg content search failed: {e}", file=sys.stderr)
        return {}

    hits = defaultdict(lambda: {"count": 0, "samples": [], "terms": set(), "lines_data": []})
    for line in proc.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg_type = obj.get("type")
        if msg_type not in ("match", "context"):
            continue
        d = obj.get("data", {})
        path = d.get("path", {}).get("text")
        if not path:
            continue
        rec = hits[path]
        text = (d.get("lines", {}).get("text") or "").rstrip("\n")
        lineno = d.get("line_number", 0)

        if msg_type == "match":
            rec["count"] += 1
            col = 0
            if extract_column and d.get("submatches"):
                # Get column of first match
                col = d["submatches"][0].get("start", 0) + 1  # 1-indexed
            
            for sm in d.get("submatches", []):
                mt = (sm.get("match") or {}).get("text")
                if mt:
                    rec["terms"].add(mt.lower()[:40])
            if len(rec["samples"]) < max_per_file:
                sample = (lineno, text[:220] + "…" if len(text) > 220 else text, col) if extract_column else (lineno, text[:220] + "…" if len(text) > 220 else text)
                rec["samples"].append(sample)
            rec["lines_data"].append((lineno, text, True, col) if extract_column else (lineno, text, True))
        else: # context
            rec["lines_data"].append((lineno, text, False, 0) if extract_column else (lineno, text, False))

    return dict(hits)

# ---------------------------------------------------------------------------
# Pure-Python Fallback Engine (with Decompression & Context Support)
# ---------------------------------------------------------------------------
def py_fallback_files(roots, ext_filter, extra_excludes, type_globs, max_depth=None, include_dirs=False, include_hidden=False, globs=()):
    excl_names = {g for g in EXCLUDE_GLOBS if "*" not in g} | set(extra_excludes)
    excl_prefix = tuple(g[:-1] for g in EXCLUDE_GLOBS if g.endswith("*"))
    files = []
    for root in roots:
        root_path = Path(root)
        root_depth = len(root_path.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            if not include_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                filenames = [f for f in filenames if not f.startswith('.')]
            if max_depth is not None:
                cur_depth = len(Path(dirpath).parts) - root_depth
                if cur_depth >= max_depth:
                    dirnames.clear()
            dirnames[:] = [d for d in dirnames if d not in excl_names and not d.startswith(excl_prefix)]
            if include_dirs and dirpath != str(root):
                files.append(dirpath)
            for fn in filenames:
                ext = Path(fn).suffix.lower()
                if ext_filter and ext not in ext_filter:
                    continue
                files.append(os.path.join(dirpath, fn))
    if globs:
        files = _apply_user_globs(files, globs, is_dir=False)
    return files

def py_fallback_content(pattern, files, regex, ignore_case, case_sensitive, word_regexp,
                        max_per_file, search_zip=False, context_before=0, context_after=0,
                        invert_match=False):
    import re
    flags = re.IGNORECASE if (ignore_case and not case_sensitive) else 0
    if word_regexp:
        pattern = r"\b" + (pattern if regex else re.escape(pattern)) + r"\b"
        matcher = re.compile(pattern, flags).search
    elif regex:
        matcher = re.compile(pattern, flags).search
    else:
        needle = pattern.lower() if flags else pattern
        matcher = (lambda s: needle in s.lower()) if flags else (lambda s: pattern in s)

    hits = {}
    for fp in files:
        if not search_zip and is_binary_file(fp):
            continue
        try:
            lines = []
            if search_zip and fp.endswith((".gz", ".tgz")):
                with gzip.open(fp, "rt", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            elif search_zip and fp.endswith(".bz2"):
                with bz2.open(fp, "rt", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            elif search_zip and fp.endswith(".xz"):
                with lzma.open(fp, "rt", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            else:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()

            match_indices = []
            for i, line in enumerate(lines):
                is_m = bool(matcher(line))
                if invert_match:
                    is_m = not is_m
                if is_m:
                    match_indices.append(i)

            if not match_indices:
                continue

            samples = []
            lines_data = []
            for idx in match_indices:
                if len(samples) < max_per_file:
                    s = lines[idx].strip()
                    samples.append((idx + 1, s[:220] + "…" if len(s) > 220 else s))

            # build context windows
            included_lines = set()
            for idx in match_indices:
                start = max(0, idx - context_before)
                end = min(len(lines), idx + context_after + 1)
                for li in range(start, end):
                    included_lines.add(li)

            for li in sorted(included_lines):
                lines_data.append((li + 1, lines[li].rstrip("\n"), li in match_indices))

            hits[fp] = {
                "count": len(match_indices),
                "samples": samples,
                "terms": {pattern.lower()[:40]},
                "lines_data": lines_data,
            }
        except (OSError, UnicodeError):
            continue
    return hits

# ---------------------------------------------------------------------------
# Name Matching Engine
# ---------------------------------------------------------------------------
def match_names(query, files, regex, ignore_case, fuzzy):
    scored = []
    rx = None
    if regex:
        rx = re.compile(query, re.IGNORECASE if ignore_case else 0)
    q = query.lower() if (ignore_case or fuzzy) else query
    for fp in files:
        base = os.path.basename(fp)
        b = base.lower() if (ignore_case or fuzzy) else base
        p = fp.lower() if (ignore_case or fuzzy) else fp
        score = 0.0
        if regex and rx:
            if rx.search(base):
                score = 3.0
            elif rx.search(fp):
                score = 1.5
        else:
            if q == b or q + Path(base).suffix.lower() == b:
                score = 5.0
            elif q in b:
                score = 3.0
            elif q in p:
                score = 1.5
            elif fuzzy:
                r = SequenceMatcher(None, q, b).ratio()
                if r >= 0.6 or all(c in iter(b) for c in q):
                    score = 0.5 + r
        if score > 0:
            scored.append((fp, score))
    scored.sort(key=lambda t: (-t[1], t[0]))
    return scored

# ---------------------------------------------------------------------------
# Multi-Signal RRF Fusion Engine
# ---------------------------------------------------------------------------
def rrf_fuse(rankings, k, weights=None):
    w_map = weights or RRF_WEIGHTS_DEFAULT
    fused = defaultdict(float)
    sources = defaultdict(list)
    for label, ranked in rankings.items():
        w = w_map.get(label, 1.0)
        for rank, path in enumerate(ranked, start=1):
            fused[path] += w / (k + rank)
            sources[path].append(label)
    out = [(p, s, sources[p]) for p, s in fused.items()]
    out.sort(key=lambda t: (-t[1], t[0]))
    return out

# ---------------------------------------------------------------------------
# Chroma Second Brain Semantic Seam
# ---------------------------------------------------------------------------
def semantic_brain(query, collection, top_k):
    try:
        import chromadb
    except ImportError:
        print("pfind: --brain semantic needs chromadb (import failed); using lexical only.", file=sys.stderr)
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
    except Exception as e:
        print(f"pfind: semantic query degraded ({type(e).__name__}: {str(e)[:100]}); lexical only.", file=sys.stderr)
        return []

# ---------------------------------------------------------------------------
# Tree View Engine (from eza-0.23.5 src/output/tree.rs)
# ---------------------------------------------------------------------------
def render_tree_view(fused_paths, content_hits, git_cache, args, use_color):
    if not fused_paths:
        return
    # Build Trie
    tree = {}
    for p in fused_paths:
        parts = Path(p).parts
        curr = tree
        for part in parts:
            curr = curr.setdefault(part, {})

    def walk_tree(node, prefix="", current_path=Path(), depth=0):
        # Apply level limiting if specified
        if args.level is not None and depth >= args.level:
            return
        
        items = sorted(node.keys())
        for i, name in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "
            full_path = current_path / name
            full_path_str = str(full_path)

            icon = get_file_icon(full_path_str, is_dir=bool(node[name])) if args.icons else ""
            git_st = git_cache.get_status(full_path_str) if git_cache and args.git else None
            git_badge = f" {c('31;1', f'[{git_st}]', use_color)}" if git_st else ""

            display_name = c("1;34", name, use_color) if node[name] else c("1;32", name, use_color)
            if args.hyperlink:
                display_name = make_hyperlink(full_path_str, 0, display_name, True, args.hyperlink_format)

            print(f"{prefix}{connector}{icon + ' ' if icon else ''}{display_name}{git_badge}")

            # print match samples under leaf files
            if not node[name] and full_path_str in content_hits:
                samples = content_hits[full_path_str].get("samples", [])
                for lineno, text in samples:
                    print(f"{prefix}{child_prefix}    {c('90', f'{lineno}:', use_color)} {text}")

            walk_tree(node[name], prefix + child_prefix, full_path, depth + 1)

    # find common roots
    walk_tree(tree)

# ---------------------------------------------------------------------------
# Code Summary View Engine (from eza-0.23.5 src/loc/mod.rs)
# ---------------------------------------------------------------------------
def render_code_summary_table(files, use_color):
    summary = defaultdict(LocCounts)
    for fp in files:
        res = classify_file_loc(fp)
        if res:
            lang_name, counts = res
            summary[lang_name].add(counts)

    if not summary:
        print("pfind: no source code files identified for --code summary.", file=sys.stderr)
        return

    print(f"\n{c('1;37', 'Language Breakdown & Lines of Code Summary:', use_color)}")
    print(f"{'-' * 70}")
    print(f"{'Language':<24} {'Total Lines':>12} {'Code':>10} {'Comments':>10} {'Blanks':>10}")
    print(f"{'-' * 70}")

    grand_total = LocCounts()
    for lang, counts in sorted(summary.items(), key=lambda kv: -kv[1].code):
        grand_total.add(counts)
        lang_str = f"{lang:<24}"
        code_str = f"{counts.code:>10,d}"
        comm_str = f"{counts.comments:>10,d}"
        blnk_str = f"{counts.blanks:>10,d}"
        print(f"{c('1;36', lang_str, use_color)} {counts.lines:>12,d} "
              f"{c('32', code_str, use_color)} "
              f"{c('33', comm_str, use_color)} "
              f"{c('90', blnk_str, use_color)}")

    print(f"{'=' * 70}")
    tot_lang = f"{'TOTAL':<24}"
    tot_code = f"{grand_total.code:>10,d}"
    tot_comm = f"{grand_total.comments:>10,d}"
    tot_blnk = f"{grand_total.blanks:>10,d}"
    print(f"{c('1;37', tot_lang, use_color)} {grand_total.lines:>12,d} "
          f"{c('1;32', tot_code, use_color)} "
          f"{c('1;33', tot_comm, use_color)} "
          f"{c('1;90', tot_blnk, use_color)}\n")

# ---------------------------------------------------------------------------
# Directory Size & Color Scale Engines (from eza-0.23.5)
# ---------------------------------------------------------------------------
_DIR_SIZE_CACHE = {}
def get_dir_total_size(path):
    """Recursively calculate total bytes contained in a directory."""
    if path in _DIR_SIZE_CACHE:
        return _DIR_SIZE_CACHE[path]
    total = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    total += os.lstat(fp).st_size
                except OSError:
                    pass
    except OSError:
        pass
    _DIR_SIZE_CACHE[path] = total
    return total

def get_scale_color(val, kind="size", use_color=True):
    """Calculate ANSI color code based on size magnitude or recency delta."""
    if not use_color:
        return ""
    if kind == "size":
        if val < 1024:
            return "32"           # < 1 KiB: green
        elif val < 1024 * 1024:
            return "36"           # < 1 MiB: cyan
        elif val < 100 * 1024 * 1024:
            return "33"           # < 100 MiB: yellow
        else:
            return "31"           # >= 100 MiB: red
    elif kind == "age":
        if val < 3600:
            return "1;32"         # < 1 hour: bright green
        elif val < 86400:
            return "32"           # < 1 day: green
        elif val < 86400 * 7:
            return "36"           # < 1 week: cyan
        elif val < 86400 * 30:
            return "33"           # < 1 month: yellow
        else:
            return "90"           # > 1 month: dim
    return ""

# ---------------------------------------------------------------------------
# Long Details View Engine (from eza-0.23.5 src/output/table.rs)
# ---------------------------------------------------------------------------
def render_long_table(paths, content_hits, git_cache, args, use_color):
    # Print header if requested
    if args.header:
        header_parts = []
        if args.inode:
            header_parts.append(f"{'INODE':<10}")
        if args.blocks:
            header_parts.append(f"{'BLOCKS':<10}")
        if args.links:
            header_parts.append(f"{'LINKS':<6}")
        header_parts.append(f"{'PERMISSIONS':<10}")
        header_parts.append(f"{'GIT':<3}")
        header_parts.append(f"{'USER':<8}")
        header_parts.append(f"{'GROUP':<8}")
        header_parts.append(f"{'SIZE':>9}")
        header_parts.append(f"{'MODIFIED':<12}")
        header_parts.append("NAME")
        print(c("1;37", " ".join(header_parts), use_color))
    
    for path in paths:
        try:
            st = os.lstat(path)
            is_dir = stat.S_ISDIR(st.st_mode)
            
            # Build metadata columns
            meta_cols = []
            if args.inode:
                meta_cols.append(f"{st.st_ino:<10}")
            if args.blocks:
                blocks = st.st_blocks if hasattr(st, 'st_blocks') else 0
                meta_cols.append(f"{blocks:<10}")
            if args.links:
                meta_cols.append(f"{st.st_nlink:<6}")
            
            mode_str = format_permissions(st.st_mode, args.octal_permissions)
            
            # Handle size display modes
            if getattr(args, 'total_size', False) and is_dir:
                raw_size = get_dir_total_size(path)
            else:
                raw_size = st.st_size

            if args.bytes:
                size_str = str(raw_size)
            else:
                size_str = format_size(raw_size, not args.metric_units)
            
            time_str = format_timestamp(st.st_mtime, args.time_style)
            user_str = pwd.getpwuid(st.st_uid).pw_name if hasattr(pwd, "getpwuid") else str(st.st_uid)
            group_str = grp.getgrgid(st.st_gid).gr_name if hasattr(grp, "getgrgid") else str(st.st_gid)
            icon = get_file_icon(path, is_dir) if args.icons else ""
            git_st = git_cache.get_status(path) if git_cache and args.git else None
            git_badge = f"{c('31;1', f'{git_st:<3}', use_color)}" if git_st else "   "

            loc_badge = ""
            if args.loc:
                loc_res = classify_file_loc(path)
                if loc_res:
                    _, lc = loc_res
                    loc_badge = f" [code:{lc.code} com:{lc.comments}]"

            path_display = make_hyperlink(path, 0, path, args.hyperlink, args.hyperlink_format)
            
            # Colors
            if getattr(args, 'color_scale', False):
                size_color = get_scale_color(raw_size, "size", use_color)
                time_color = get_scale_color(time.time() - st.st_mtime, "age", use_color)
            else:
                size_color = "33"
                time_color = "36"

            meta_prefix = " ".join(meta_cols) + " " if meta_cols else ""
            print(f"{meta_prefix}{c('90', f'{mode_str:<10}', use_color)} {git_badge} {user_str:<8} {group_str:<8} "
                  f"{c(size_color, f'{size_str:>9}', use_color)} {c(time_color, f'{time_str:<12}', use_color)} "
                  f"{icon + ' ' if icon else ''}{c('1;32', path_display, use_color)}{loc_badge}")

            if path in content_hits:
                for lineno, text in content_hits[path].get("samples", []):
                    line_display = make_hyperlink(path, lineno, f"{lineno}:", args.hyperlink, args.hyperlink_format)
                    print(f"    {c('90', line_display, use_color)} {text}")
        except OSError:
            print(path)

# ---------------------------------------------------------------------------
# Grid Layout Rendering (from eza-0.23.5 src/output/grid.rs)
# ---------------------------------------------------------------------------
def render_grid(paths, use_color, args, terminal_width=None):
    """Render paths in multi-column grid layout."""
    if not paths:
        return
    
    if terminal_width is None:
        terminal_width = shutil.get_terminal_size((80, 24)).columns
    
    # Calculate column width based on longest path
    max_len = max((len(os.path.basename(p)) for p in paths), default=0)
    icon_width = 2 if args.icons else 0
    col_width = max_len + icon_width + 2  # padding
    
    if col_width == 0:
        col_width = 20
    
    num_cols = max(1, terminal_width // col_width)
    
    for i, path in enumerate(paths):
        icon = get_file_icon(path, os.path.isdir(path)) if args.icons else ""
        basename = os.path.basename(path)
        is_dir = os.path.isdir(path)
        
        display_name = c("1;34", basename, use_color) if is_dir else basename
        output = f"{icon + ' ' if icon else ''}{display_name}"
        
        if (i + 1) % num_cols == 0:
            print(output)
        else:
            print(output.ljust(col_width), end="")
    
    # Final newline if needed
    if len(paths) % num_cols != 0:
        print()

# ---------------------------------------------------------------------------
# Oneline Rendering (from eza-0.23.5)
# ---------------------------------------------------------------------------
def render_oneline(paths, use_color, args):
    """Render one entry per line (simple list)."""
    for path in paths:
        icon = get_file_icon(path, os.path.isdir(path)) if args.icons else ""
        is_dir = os.path.isdir(path)
        
        if args.long:
            # Simple long format
            try:
                st = os.lstat(path)
                size_str = format_size(st.st_size, not args.metric_units)
                display_name = c("1;34", path, use_color) if is_dir else c("1;32", path, use_color)
                print(f"{icon + ' ' if icon else ''}{display_name:<60} {c('33', size_str, use_color)}")
            except OSError:
                print(path)
        else:
            display_name = c("1;34", path, use_color) if is_dir else path
            if args.null:
                print(f"{icon + ' ' if icon else ''}{display_name}", end="\0")
            else:
                print(f"{icon + ' ' if icon else ''}{display_name}")

# ---------------------------------------------------------------------------
# Vimgrep Format Rendering (from ripgrep-15.2.0)
# ---------------------------------------------------------------------------
def render_vimgrep(content_hits, use_color, args):
    """Render in vimgrep format: file:line:col:match"""
    items = sorted(content_hits.items())
    if args.limit:
        items = items[:args.limit]
    for path, hit_data in items:
        lines_data = hit_data.get("lines_data", [])
        if not lines_data:
            # Fall back to samples
            for sample in hit_data.get("samples", []):
                if len(sample) == 3:  # Has column info
                    lineno, text, col = sample
                    print(f"{path}:{lineno}:{col}:{text}")
                else:
                    lineno, text = sample
                    col = 1  # Default column
                    print(f"{path}:{lineno}:{col}:{text}")
        else:
            for line_info in lines_data:
                if len(line_info) == 4:  # Has column info
                    lineno, text, is_match, col = line_info
                else:
                    lineno, text, is_match = line_info
                    col = 1
                
                if is_match:  # Only output match lines, not context
                    print(f"{path}:{lineno}:{col}:{text}")

# ---------------------------------------------------------------------------
# Regex Replacement Preview (from ripgrep-15.2.0)
# ---------------------------------------------------------------------------
def apply_replacement_preview(line_text, replacement_pattern, pattern=None, is_regex=False):
    """Apply replacement pattern to occurrences of pattern in line_text.
    Supports $1, $2, ${name} capture groups when is_regex=True."""
    if not replacement_pattern:
        return line_text
    if pattern:
        try:
            if is_regex:
                rg_repl = re.sub(r'\$(\d+)', r'\\\1', replacement_pattern)
                rg_repl = re.sub(r'\$\{(\w+)\}', r'\\g<\1>', rg_repl)
                return re.sub(pattern, rg_repl, line_text)
            else:
                return line_text.replace(pattern, replacement_pattern)
        except Exception:
            return line_text
    return replacement_pattern

# ---------------------------------------------------------------------------
# Standard Ranked Rendering Engine
# ---------------------------------------------------------------------------
def render(fused, name_scores, content_hits, git_cache, args, use_color, query_pattern=None):
    if not fused:
        print("no matches.", file=sys.stderr)
        return 0

    # Extract paths
    paths = [p for p, _, _ in fused]
    
    # Apply file/directory filtering
    if args.only_dirs:
        paths = [p for p in paths if os.path.isdir(p)]
    elif args.only_files:
        paths = [p for p in paths if os.path.isfile(p)]
    
    # Apply symlink filtering
    if args.no_symlinks:
        paths = [p for p in paths if not os.path.islink(p)]
    
    # Apply files-with-matches / files-without-match filtering
    if args.files_with_matches:
        paths = [p for p in paths if p in content_hits and content_hits[p].get("count", 0) > 0]
        for p in paths:
            if args.null:
                print(p, end="\0")
            else:
                print(p)
        return 0
    elif args.files_without_match:
        paths = [p for p in paths if p not in content_hits or content_hits[p].get("count", 0) == 0]
        for p in paths:
            if args.null:
                print(p, end="\0")
            else:
                print(p)
        return 0
    
    # Handle count modes
    if args.count_lines or args.count_matches:
        for path in paths:
            if path in content_hits:
                if args.count_matches:
                    count = content_hits[path].get("count", 0)
                else:  # count_lines
                    count = len(content_hits[path].get("samples", []))
                print(f"{count}:{path}")
            elif args.include_zero:
                print(f"0:{path}")
        return 0
    
    # Handle quiet mode (exit code only)
    if args.quiet:
        return 0 if paths else 1
    
    # Rebuild fused with filtered paths
    path_to_data = {p: (s, l) for p, s, l in fused}
    fused = [(p, path_to_data[p][0], path_to_data[p][1]) for p in paths if p in path_to_data]
    
    if not fused:
        print("no matches.", file=sys.stderr)
        return 0
    
    # Handle vimgrep format
    if args.vimgrep:
        render_vimgrep(content_hits, use_color, args)
        return 0
    
    # Handle grid layout
    if args.grid:
        render_grid(paths, use_color, args)
        return 0
    
    # Handle oneline layout
    if args.oneline:
        render_oneline(paths, use_color, args)
        return 0

    # Handle tree view
    if args.tree:
        render_tree_view(paths, content_hits, git_cache, args, use_color)
        return 0

    # Handle long table
    if args.long:
        render_long_table(paths, content_hits, git_cache, args, use_color)
        return 0

    # Standard ranked output
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
        if "git" in labels:
            why.append(c("31", "dirty", use_color))

        tag = ",".join(why)
        icon = get_file_icon(path) if args.icons else ""
        git_st = git_cache.get_status(path) if git_cache and args.git else None
        git_badge = f" {c('31;1', f'[{git_st}]', use_color)}" if git_st else ""

        loc_badge = ""
        if args.loc:
            loc_res = classify_file_loc(path)
            if loc_res:
                _, lc = loc_res
                loc_badge = f" {c('90', f'(LOC: {lc.code} code, {lc.comments} com)', use_color)}"

        path_display = make_hyperlink(path, 0, path, args.hyperlink, args.hyperlink_format)
        header = f"{c('90', f'{score:6.4f}', use_color)}  [{tag}]  {icon + ' ' if icon else ''}{c('1;32', path_display, use_color)}{git_badge}{loc_badge}"

        if args.files_only:
            if args.null:
                print(path, end="\0")
            else:
                print(path)
            continue

        # Format path with custom path_separator if specified
        out_path = path.replace("/", args.path_separator).replace("\\", args.path_separator) if getattr(args, 'path_separator', None) else path
        match_sep = getattr(args, 'field_match_separator', ':') or ':'
        ctx_sep = getattr(args, 'field_context_separator', '-') or '-'
        ctx_divider = "" if getattr(args, 'no_context_separator', False) else (getattr(args, 'context_separator', '--') or '--')

        # Handle heading vs no-heading modes
        if args.no_heading:
            # Prefix each line with filename
            hit_data = content_hits.get(path, {})
            if args.context > 0 or args.after_context > 0 or args.before_context > 0:
                lines_data = hit_data.get("lines_data", [])
                for line_info in lines_data:
                    if len(line_info) == 4:  # Has column info
                        lineno, text, is_match, col = line_info
                    else:
                        lineno, text, is_match = line_info
                        col = 0
                    
                    sep = match_sep if is_match else ctx_sep
                    if args.column and col > 0 and not args.no_line_number:
                        lineno_disp = f"{out_path}{sep}{lineno}{sep}{col}{sep}"
                    elif not args.no_line_number:
                        lineno_disp = f"{out_path}{sep}{lineno}{sep}"
                    else:
                        lineno_disp = f"{out_path}{sep}"
                    
                    if args.replace and is_match:
                        # Apply replacement preview
                        text = apply_replacement_preview(text, args.replace, query_pattern, args.regex)
                    print(f"{lineno_disp} {text}")
            else:
                for sample in hit_data.get("samples", []):
                    if len(sample) == 3:  # Has column info
                        lineno, text, col = sample
                    else:
                        lineno, text = sample
                        col = 0
                    
                    if args.column and col > 0 and not args.no_line_number:
                        lineno_disp = f"{out_path}{match_sep}{lineno}{match_sep}{col}{match_sep}"
                    elif not args.no_line_number:
                        lineno_disp = f"{out_path}{match_sep}{lineno}{match_sep}"
                    else:
                        lineno_disp = f"{out_path}{match_sep}"
                    
                    if args.replace:
                        text = apply_replacement_preview(text, args.replace, query_pattern, args.regex)
                    print(f"{lineno_disp} {text}")
        else:
            # Default: heading mode
            print(header)
            if not args.names:
                hit_data = content_hits.get(path, {})
                # If context windows exist, print formatted blocks
                if args.context > 0 or args.after_context > 0 or args.before_context > 0:
                    lines_data = hit_data.get("lines_data", [])
                    last_line = None
                    for line_info in lines_data:
                        if len(line_info) == 4:  # Has column info
                            lineno, text, is_match, col = line_info
                        else:
                            lineno, text, is_match = line_info
                            col = 0
                        
                        if last_line is not None and lineno > last_line + 1 and ctx_divider:
                            print(f"    {c('90', ctx_divider, use_color)}")
                        last_line = lineno
                        
                        sep = match_sep if is_match else ctx_sep
                        if args.column and col > 0:
                            lineno_disp = make_hyperlink(path, lineno, f"{lineno}{sep}{col}{sep}", args.hyperlink, args.hyperlink_format) if not args.no_line_number else ""
                        else:
                            lineno_disp = make_hyperlink(path, lineno, f"{lineno}{sep}", args.hyperlink, args.hyperlink_format) if not args.no_line_number else ""
                        
                        if args.replace and is_match:
                            text = apply_replacement_preview(text, args.replace, query_pattern, args.regex)
                        if is_match:
                            print(f"    {c('1;33', lineno_disp, use_color)} {text}")
                        else:
                            print(f"    {c('90', lineno_disp, use_color)} {text}")
                else:
                    for sample in hit_data.get("samples", []):
                        if len(sample) == 3:  # Has column info
                            lineno, text, col = sample
                            lineno_disp = make_hyperlink(path, lineno, f"{lineno}{match_sep}{col}{match_sep}", args.hyperlink, args.hyperlink_format) if args.column and not args.no_line_number else make_hyperlink(path, lineno, f"{lineno}{match_sep}", args.hyperlink, args.hyperlink_format) if not args.no_line_number else ""
                        else:
                            lineno, text = sample
                            lineno_disp = make_hyperlink(path, lineno, f"{lineno}{match_sep}", args.hyperlink, args.hyperlink_format) if not args.no_line_number else ""
                        
                        if args.replace:
                            text = apply_replacement_preview(text, args.replace, query_pattern, args.regex)
                        print(f"    {c('90', lineno_disp, use_color)} {text}")

    if args.count:
        print(f"\n--- {len(fused)} file(s) matched"
              + (f", showing {shown}" if args.limit and len(fused) > shown else "")
              + " ---", file=sys.stderr)
    return 0

# ---------------------------------------------------------------------------
# Exact & Loose Snippet Search
# ---------------------------------------------------------------------------
def build_loose_regex(snippet):
    parts = [re.escape(tok) for tok in snippet.split()]
    return r"\s+".join(p for p in parts if p)

# ---------------------------------------------------------------------------
# File Sorting
# ---------------------------------------------------------------------------
def sort_files(files, sort_by, reverse=False, dirs_first=False, dirs_last=False):
    """Sort files by specified field with optional directory grouping."""
    if not sort_by or sort_by == "none":
        files_list = list(files)
    else:
        def get_sort_key(path):
            try:
                st = os.stat(path)
                if sort_by == "modified":
                    return st.st_mtime
                elif sort_by == "accessed":
                    return st.st_atime
                elif sort_by == "created":
                    return st.st_ctime if hasattr(st, 'st_ctime') else st.st_mtime
                elif sort_by == "path":
                    return path
                else:
                    return path
            except OSError:
                return 0 if sort_by != "path" else path
        
        files_list = sorted(files, key=get_sort_key, reverse=reverse)
    
    # Apply directory grouping
    if dirs_first:
        dirs = [f for f in files_list if os.path.isdir(f)]
        files_only = [f for f in files_list if not os.path.isdir(f)]
        return dirs + files_only
    elif dirs_last:
        dirs = [f for f in files_list if os.path.isdir(f)]
        files_only = [f for f in files_list if not os.path.isdir(f)]
        return files_only + dirs
    
    return files_list

# ---------------------------------------------------------------------------
# Language Type Listing
# ---------------------------------------------------------------------------
def print_type_list():
    """Print all language type definitions and exit."""
    print("Language types supported:")
    print()
    for lang, exts in sorted(LANGUAGE_TYPES.items()):
        print(f"  {lang:20s} {', '.join(exts)}")
    print()
    print(f"Total: {len(LANGUAGE_TYPES)} language types")
    print("Usage: pfind 'pattern' -t python -t rust")

# ---------------------------------------------------------------------------
# CLI Argument Parser Definition
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="pfind",
        description=f"Unified hybrid ranked search & exploration powerhouse — tuned for {MACHINE}.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="presets: --brain --work --src --all | engines: ripgrep-15.2.0 + eza-0.23.5 + pfind RRF"
    )
    p.add_argument("query", nargs="?", default=None, help="what to find (literal substring, regex, or snippet)")
    p.add_argument("paths", nargs="*", help="roots to search (default: cwd, or a preset)")

    # presets
    p.add_argument("--brain", action="store_true", help="search ~/Documents/SECOND.BRAIN + Chroma semantic seam")
    p.add_argument("--work", action="store_true", help="search ~/Documents/FIREFOX.WORK toolkit")
    p.add_argument("--src", action="store_true", help="search ~/firefox-main source tree")
    p.add_argument("--all", action="store_true", help="search brain + work + src in one shot")

    # search modes
    p.add_argument("-r", "--regex", action="store_true", help="treat query as a regex")
    p.add_argument("-F", "--fixed-strings", action="store_true", help="treat query as a literal string (default)")
    p.add_argument("-i", "--ignore-case", action="store_true", help="force case-insensitive")
    p.add_argument("-s", "--case-sensitive", action="store_true", help="force strict case-sensitive")
    p.add_argument("-S", "--smart-case", action="store_true", help="smart case sensitivity (default)")
    p.add_argument("-w", "--word-regexp", action="store_true", help="match whole words only")
    p.add_argument("-x", "--exact", action="store_true", help="exact multi-line snippet: literal match, spans newlines")
    p.add_argument("--loose", action="store_true", help="snippet match tolerant of whitespace/indent drift")
    p.add_argument("--fuzzy", action="store_true", help="typo/partial-tolerant name matching")
    p.add_argument("-v", "--invert-match", action="store_true", help="select non-matching lines")
    p.add_argument("--pcre2", action="store_true", help="enable PCRE2 regex engine")

    # context & sinks
    p.add_argument("-C", "--context", type=int, default=0, help="show NUM lines before and after match")
    p.add_argument("-A", "--after-context", type=int, default=0, help="show NUM lines after match")
    p.add_argument("-B", "--before-context", type=int, default=0, help="show NUM lines before match")
    p.add_argument("--context-separator", type=str, default="--", help="separator between context blocks (default: --)")
    p.add_argument("--no-context-separator", action="store_true", help="suppress separator between context blocks")
    p.add_argument("--field-context-separator", type=str, default="-", help="separator for context line numbers (default: -)")
    p.add_argument("--field-match-separator", type=str, default=":", help="separator for match line numbers (default: :)")
    p.add_argument("--path-separator", type=str, default=None, help="override path separator in output")
    p.add_argument("-o", "--only-matching", action="store_true", help="show only matching parts")
    p.add_argument("--replace", type=str, default=None, help="show regex replacement preview ($1, $name, ${1})")
    p.add_argument("-m", "--max-count", type=int, default=0, help="max matches per file")
    p.add_argument("-c", "--count-lines", action="store_true", help="count matching lines per file")
    p.add_argument("--count-matches", action="store_true", help="count individual matches (not lines)")
    p.add_argument("--include-zero", action="store_true", help="with --count, show files with 0 matches too")

    # scope & types
    p.add_argument("-t", "--type", action="append", dest="types", help="filter by language type (rust, py, c, etc.)")
    p.add_argument("--type-not", action="append", dest="types_not", help="exclude language type")
    p.add_argument("--type-add", action="append", dest="type_adds", metavar="SPEC", help="add custom language type e.g. 'pdf:*.pdf'")
    p.add_argument("--type-clear", action="append", dest="type_clears", metavar="TYPE", help="clear language type globs (or 'all')")
    p.add_argument("--type-list", action="store_true", help="list all language type definitions and exit")
    p.add_argument("--pre", type=str, default=None, help="pipe candidate files through external preprocessor")
    p.add_argument("--pre-glob", type=str, default=None, help="only apply --pre to matching files")
    p.add_argument("--ext", nargs="+", metavar="EXT", help="only these extensions (.py .sh ...)")
    p.add_argument("--exclude", nargs="+", metavar="GLOB", default=[], help="extra excludes")
    p.add_argument("-g", "--glob", action="append", dest="globs", default=[], help="include/exclude glob (repeatable)")
    p.add_argument("-e", "--regexp", action="append", dest="patterns", default=[], help="additional pattern (repeatable, OR logic)")
    p.add_argument("-f", "--pattern-file", type=str, help="read patterns from file (one per line)")
    p.add_argument("-z", "--search-zip", action="store_true", help="search inside compressed archives (.gz, .zip, etc.)")
    p.add_argument("-a", "--text", action="store_true", help="treat binary files as text (no NUL filtering)")
    p.add_argument("--binary", action="store_true", help="search binary files but warn on NUL bytes")
    p.add_argument("--hidden", action="store_true", help="include hidden files")
    p.add_argument("--no-ignore", action="store_true", help="ignore .gitignore and .ignore rules")
    p.add_argument("--no-ignore-dot", action="store_true", help="don't respect .ignore / .rgignore")
    p.add_argument("--no-ignore-global", action="store_true", help="don't respect ~/.config/git/ignore")
    p.add_argument("--no-ignore-parent", action="store_true", help="don't ascend for ignore files")
    p.add_argument("--no-ignore-vcs", action="store_true", help="ignore .gitignore but keep .ignore")
    p.add_argument("-u", "--unrestricted", action="count", default=0, help="-u skip ignores; -uu +hidden; -uuu +binary")
    p.add_argument("-d", "--max-depth", type=int, default=None, help="max directory descent depth")
    p.add_argument("--max-filesize", type=str, help="skip files larger than NUM (bytes, K, M, G)")
    p.add_argument("--one-file-system", action="store_true", help="don't cross filesystem boundaries")

    # presentation & eza views
    p.add_argument("-l", "--long", action="store_true", help="show detailed file metadata table")
    p.add_argument("-T", "--tree", action="store_true", help="render hierarchical directory tree")
    p.add_argument("--level", type=int, default=None, help="max tree depth (for --tree)")
    p.add_argument("-R", "--recurse", action="store_true", help="flat recursive listing (no tree connectors)")
    p.add_argument("-G", "--grid", action="store_true", help="multi-column grid layout")
    p.add_argument("-1", "--oneline", action="store_true", help="one entry per line")
    p.add_argument("--loc", action="store_true", help="calculate comment-aware lines of code")
    p.add_argument("--code", action="store_true", help="output aggregated code/comment/blank summary table")
    p.add_argument("--git", action="store_true", default=True, help="display Git status flags (default: on)")
    p.add_argument("--no-git", action="store_true", help="suppress all git columns")
    p.add_argument("--git-dirty", action="store_true", help="filter/boost modified Git files")
    p.add_argument("--dirty-boost", action="store_true", help="boost uncommitted Git files in RRF ranking")
    p.add_argument("--recency-boost", action="store_true", help="boost recently modified files in RRF ranking")
    p.add_argument("--color-scale", action="store_true", help="highlight size and recency with adaptive color scales")
    p.add_argument("--color-scale-mode", choices=["fixed", "gradient"], default="fixed", help="color scale mode (fixed|gradient)")
    p.add_argument("--total-size", action="store_true", help="calculate directory size as sum of contents")
    p.add_argument("--time", choices=["modified", "accessed", "created"], default="modified", help="timestamp type")
    p.add_argument("--time-style", choices=["relative", "iso", "default"], default="relative", help="timestamp format")
    p.add_argument("--octal-permissions", action="store_true", help="show numeric octal permissions")
    p.add_argument("--blocks", action="store_true", help="show allocated filesystem blocks")
    p.add_argument("--inode", action="store_true", help="show inode number")
    p.add_argument("--links", action="store_true", help="show hard link count")
    p.add_argument("--metric-units", action="store_true", help="use 1000-based metric units instead of 1024 binary")
    p.add_argument("--binary-units", action="store_true", help="use 1024-based binary units (KiB, MiB) - default")
    p.add_argument("--bytes", action="store_true", help="show raw byte count (no unit prefix)")
    p.add_argument("--header", action="store_true", help="show column header row")
    p.add_argument("--icons", action="store_true", help="display Nerd Font file icons")
    p.add_argument("--hyperlink", action="store_true", help="emit OSC 8 clickable terminal hyperlinks")
    p.add_argument("--hyperlink-format", type=str, default="file", choices=["file", "vscode", "grep+"], 
                   help="OSC 8 hyperlink format (file, vscode, grep+)")
    
    # filtering & sorting (eza)
    p.add_argument("--dirs-first", action="store_true", help="group directories before files")
    p.add_argument("--dirs-last", action="store_true", help="group directories after files")
    p.add_argument("-D", "--only-dirs", action="store_true", help="show only directories")
    p.add_argument("--only-files", action="store_true", help="show only files")
    p.add_argument("--show-symlinks", action="store_true", help="include symlinks with --only-dirs/--only-files")
    p.add_argument("--no-symlinks", action="store_true", help="exclude symlinks from listing")
    p.add_argument("--follow-symlinks", action="store_true", help="follow symlinks into directories")
    p.add_argument("--almost-all", action="store_true", help="include dotfiles, exclude . and ..")
    p.add_argument("-I", "--ignore-glob", type=str, help="pipe-separated globs to hide")
    p.add_argument("--reverse", action="store_true", help="reverse current sort order")

    # tuning & output
    p.add_argument("--names", action="store_true", help="filenames only")
    p.add_argument("--content", action="store_true", help="file contents only")
    p.add_argument("--files", action="store_true", help="list files that would be searched (no search)")
    p.add_argument("--files-with-matches", action="store_true", 
                   help="print only paths with matches")
    p.add_argument("--files-without-match", action="store_true", help="print only paths without matches")
    p.add_argument("--files-only", action="store_true", help="print paths only")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress output; use exit code only")
    p.add_argument("--no-messages", action="store_true", help="suppress file open/read errors")
    p.add_argument("--count", action="store_true", help="print match count summary")
    p.add_argument("--stats", action="store_true", help="print search performance and match statistics")
    p.add_argument("--column", action="store_true", help="show 1-based column number of first match")
    p.add_argument("-n", "--line-number", action="store_true", default=True, help="show line numbers (default)")
    p.add_argument("-N", "--no-line-number", action="store_true", help="suppress line numbers")
    p.add_argument("--heading", action="store_true", help="group under file header")
    p.add_argument("--no-heading", action="store_true", help="prefix each line with filename")
    p.add_argument("--vimgrep", action="store_true", help="file:line:col:match format (vim :cgetfile)")
    p.add_argument("-p", "--pretty", action="store_true", help="force --color=always --heading --line-number")
    p.add_argument("-0", "--null", action="store_true", help="NUL-terminate file paths")
    p.add_argument("--sort", type=str, choices=["path", "modified", "accessed", "created", "none"], 
                   help="sort results by field")
    p.add_argument("--sortr", type=str, choices=["path", "modified", "accessed", "created"], 
                   help="reverse sort by field")
    p.add_argument("--color", type=str, choices=["never", "auto", "always", "ansi"], default="auto",
                   help="color output (never|auto|always|ansi)")
    p.add_argument("--workers", type=int, default=LOGICAL_CPUS, help=f"threads (default {LOGICAL_CPUS})")
    p.add_argument("--timeout", type=int, default=600, help="timeout seconds (default 600)")
    p.add_argument("--rrf-k", type=int, default=RRF_K_DEFAULT, help=f"RRF k (default {RRF_K_DEFAULT})")
    p.add_argument("--max", type=int, default=5, help="content samples per file (default 5)")
    p.add_argument("--limit", type=int, default=40, help="max files shown (default 40; 0 = all)")
    p.add_argument("--collection", default=BRAIN_DEFAULT_COLLECTION, help="brain collection for semantic seam")
    p.add_argument("--no-color", action="store_true", help="disable ANSI color")

    return p

# ---------------------------------------------------------------------------
# Main Execution Entry Point
# ---------------------------------------------------------------------------
def main():
    start_time = time.time()
    args = build_parser().parse_args()

    # Dynamic language type manipulation
    if getattr(args, 'type_clears', None):
        for tc in args.type_clears:
            tc_lower = tc.lower()
            if tc_lower == "all":
                LANGUAGE_TYPES.clear()
            elif tc_lower in LANGUAGE_TYPES:
                del LANGUAGE_TYPES[tc_lower]
    if getattr(args, 'type_adds', None):
        for ta in args.type_adds:
            if ":" in ta:
                t_name, globs_str = ta.split(":", 1)
                exts = [g.strip() for g in globs_str.split(",") if g.strip()]
                exts_norm = [e if e.startswith(".") else ("." + e if not e.startswith("*") else e.lstrip("*")) for e in exts]
                LANGUAGE_TYPES[t_name.lower().strip()] = exts_norm

    # Early exits
    if args.type_list:
        print_type_list()
        return 0
    
    # Handle color mode
    if args.color == "never" or args.no_color:
        use_color = False
    elif args.color == "always" or args.color == "ansi":
        use_color = True
    else:  # auto
        use_color = sys.stdout.isatty() and not args.no_color
    
    # Handle --pretty flag
    if args.pretty:
        use_color = True
        args.heading = True
        args.line_number = True
    
    # Handle --no-git override
    if args.no_git:
        args.git = False
    
    # Handle -u/--unrestricted levels
    if args.unrestricted >= 1:
        args.no_ignore = True
    if args.unrestricted >= 2:
        args.hidden = True
    if args.unrestricted >= 3:
        args.text = True

    presets = [name for name in ("brain", "work", "src") if getattr(args, name)]
    if args.all:
        presets = ["brain", "work", "src"]

    # Standalone --code summary mode: all positional args are paths
    if args.code:
        path_list = list(args.paths)
        if args.query:
            path_list.insert(0, args.query)
        roots = resolve_roots(path_list, presets)
        type_globs = resolve_type_globs(args.types, args.types_not)
        all_files = (rg_list_files(roots, args.ext, args.exclude, type_globs, args.hidden, args.no_ignore, args.workers, args.max_depth, globs=args.globs)
                     if HAVE_RG else py_fallback_files(roots, set(args.ext or []), args.exclude, type_globs, args.max_depth, globs=args.globs))
        for r in roots:
            if os.path.isfile(r) and str(r) not in all_files:
                all_files.append(str(r))
        render_code_summary_table(all_files, use_color)
        return 0
    
    # --files mode: list files that would be searched (no search)
    if args.files:
        path_list = list(args.paths)
        if args.query:
            path_list.insert(0, args.query)
        roots = resolve_roots(path_list, presets)
        type_globs = resolve_type_globs(args.types, args.types_not)
        all_files = (rg_list_files(roots, args.ext, args.exclude, type_globs, args.hidden, args.no_ignore, args.workers, args.max_depth, globs=args.globs)
                     if HAVE_RG else py_fallback_files(roots, set(args.ext or []), args.exclude, type_globs, args.max_depth, globs=args.globs))
        for r in roots:
            if os.path.isfile(r) and str(r) not in all_files:
                all_files.append(str(r))
        for f in all_files:
            print(f)
        return 0

    # Exploratory Mode (zero query or explicit directory target with tree/long flags)
    is_exploratory = (not args.query or args.query == ".")
    if not is_exploratory and (args.tree or args.long) and not args.paths:
        if os.path.exists(args.query):
            args.paths = [args.query]
            args.query = None
            is_exploratory = True

    if is_exploratory:
        roots = resolve_roots(args.paths, presets)
        type_globs = resolve_type_globs(args.types, args.types_not)
        git_cache = GitStatusCache(roots) if args.git else None
        if args.only_dirs:
            all_files = py_fallback_files(roots, args.ext, args.exclude, type_globs, args.max_depth, include_dirs=True, include_hidden=args.hidden or args.almost_all, globs=args.globs)
            all_files = [f for f in all_files if os.path.isdir(f)]
        else:
            all_files = (rg_list_files(roots, args.ext, args.exclude, type_globs, args.hidden, args.no_ignore, args.workers, args.max_depth, globs=args.globs)
                         if HAVE_RG else py_fallback_files(roots, set(args.ext or []), args.exclude, type_globs, args.max_depth, include_hidden=args.hidden or args.almost_all, globs=args.globs))
            for r in roots:
                if os.path.isfile(r) and str(r) not in all_files:
                    all_files.append(str(r))
        
        # Apply filtering
        if args.only_files:
            all_files = [f for f in all_files if os.path.isfile(f)]
        
        if args.no_symlinks:
            all_files = [f for f in all_files if not os.path.islink(f)]
        
        if args.almost_all:
            # Include dotfiles but not . and ..
            # This is already handled by file enumeration, just noting it here
            pass
        
        if args.ignore_glob:
            # Apply custom ignore patterns
            ignore_patterns = args.ignore_glob.split('|')
            filtered = []
            for f in all_files:
                basename = os.path.basename(f)
                if not any(re.match(pat.replace('*', '.*'), basename) for pat in ignore_patterns):
                    filtered.append(f)
            all_files = filtered
        
        if args.git_dirty and git_cache:
            all_files = [f for f in all_files if git_cache.get_status(f)]
        
        # Apply sorting
        sort_field = args.sortr if args.sortr else args.sort
        reverse = bool(args.sortr) or args.reverse
        all_files = sort_files(all_files, sort_field, reverse, args.dirs_first, args.dirs_last)
        
        # Apply limit
        limit = args.limit if args.limit else (200 if args.tree else 100)
        all_files = all_files[:limit]
        
        # Handle output modes
        if args.recurse:
            # Flat recursive listing (no tree connectors)
            for f in all_files:
                icon = get_file_icon(f, os.path.isdir(f)) if args.icons else ""
                is_dir = os.path.isdir(f)
                display_name = c("1;34", f, use_color) if is_dir else c("1;32", f, use_color)
                if args.null:
                    print(f"{icon + ' ' if icon else ''}{display_name}", end="\0")
                else:
                    print(f"{icon + ' ' if icon else ''}{display_name}")
        elif args.grid:
            render_grid(all_files, use_color, args)
        elif args.oneline:
            render_oneline(all_files, use_color, args)
        elif args.tree:
            render_tree_view(all_files, {}, git_cache, args, use_color)
        elif args.long:
            render_long_table(all_files, {}, git_cache, args, use_color)
        else:
            render_long_table(all_files, {}, git_cache, args, use_color)
        return 0

    roots = resolve_roots(args.paths, presets)
    type_globs = resolve_type_globs(args.types, args.types_not)
    git_cache = GitStatusCache(roots) if args.git else None
    
    # Handle multiple patterns (-e/--regexp, -f/--pattern-file)
    patterns = []
    if args.query:
        patterns.append(args.query)
    if args.patterns:
        patterns.extend(args.patterns)
    if args.pattern_file:
        try:
            with open(args.pattern_file, 'r') as f:
                patterns.extend([line.strip() for line in f if line.strip()])
        except OSError as e:
            print(f"pfind: error reading pattern file: {e}", file=sys.stderr)
            return 1
    
    # If multiple patterns, combine with OR (|)
    if len(patterns) > 1:
        query = '|'.join(f'({re.escape(p) if not args.regex else p})' for p in patterns)
        args.regex = True  # Force regex mode for multiple patterns
    elif patterns:
        query = patterns[0]
    else:
        print("pfind: no query specified", file=sys.stderr)
        return 1

    # Search Mode
    snippet_mode = args.exact or args.loose or ("\n" in query)
    do_names = (not args.content) and not snippet_mode
    do_content = not args.names or snippet_mode

    if args.loose:
        pattern, use_regex, use_fixed, multiline = build_loose_regex(query), True, False, True
    elif snippet_mode:
        pattern, use_regex, use_fixed, multiline = query, False, True, True
    else:
        pattern = query
        use_regex = args.regex
        use_fixed = args.fixed_strings or (not args.regex)
        multiline = False

    # 1. Name search
    name_ranked, name_scores = [], {}
    if do_names:
        files = (rg_list_files(roots, args.ext, args.exclude, type_globs, args.hidden, args.no_ignore, args.workers, args.max_depth, globs=args.globs)
                 if HAVE_RG else py_fallback_files(roots, set(args.ext or []), args.exclude, type_globs, args.max_depth, globs=args.globs))
        scored = match_names(query, files, use_regex, args.ignore_case, args.fuzzy)
        name_ranked = [fp for fp, _ in scored]
        name_scores = dict(scored)

    # 2. Content search
    content_hits = {}
    if do_content:
        ctx_b = args.context or args.before_context
        ctx_a = args.context or args.after_context
        if HAVE_RG:
            content_hits = rg_content(
                pattern, roots, use_regex, args.ignore_case, args.case_sensitive,
                args.word_regexp, args.ext, args.exclude, type_globs, args.hidden,
                args.no_ignore, args.workers, args.max, fixed=use_fixed,
                multiline=multiline, search_zip=args.search_zip,
                context_before=ctx_b, context_after=ctx_a, max_depth=args.max_depth,
                pcre2=args.pcre2, invert_match=args.invert_match, timeout=args.timeout,
                extract_column=args.column, pre=args.pre, pre_glob=args.pre_glob,
                globs=args.globs
            )
        else:
            files = py_fallback_files(roots, set(args.ext or []), args.exclude, type_globs, args.max_depth, globs=args.globs)
            content_hits = py_fallback_content(
                pattern, files, use_regex, args.ignore_case, args.case_sensitive,
                args.word_regexp, args.max, search_zip=args.search_zip,
                context_before=ctx_b, context_after=ctx_a, invert_match=args.invert_match
            )

    # Content rank by distinct-term coverage first, then total volume
    content_ranked = [p for p, _ in sorted(
        content_hits.items(),
        key=lambda kv: (-len(kv[1].get("terms", ())), -kv[1]["count"], kv[0])
    )]

    # 3. Semantic seam (opt-in --brain)
    semantic_ranked, brain_recall = [], []
    if args.brain:
        for hit in semantic_brain(args.query, args.collection, top_k=max(args.max, 5)):
            if hit["path"]:
                if hit["path"] not in semantic_ranked:
                    semantic_ranked.append(hit["path"])
            else:
                brain_recall.append(hit)

    # 4. Optional Git Dirty & Recency signals
    git_ranked = []
    if (args.git_dirty or args.dirty_boost) and git_cache:
        all_candidates = set(name_ranked) | set(content_ranked)
        git_ranked = [p for p in all_candidates if git_cache.get_status(p)]

    recency_ranked = []
    if args.recency_boost:
        all_candidates = set(name_ranked) | set(content_ranked)
        recency_ranked = sorted(
            all_candidates,
            key=lambda p: -os.path.getmtime(p) if os.path.exists(p) else 0
        )

    # 5. Multi-Signal RRF Fusion
    rankings = {}
    if name_ranked:
        rankings["name"] = name_ranked
    if content_ranked:
        rankings["content"] = content_ranked
    if semantic_ranked:
        rankings["semantic"] = semantic_ranked
    if git_ranked:
        rankings["git"] = git_ranked
    if recency_ranked:
        rankings["recency"] = recency_ranked

    if not rankings and not brain_recall:
        if not args.quiet and not args.no_messages:
            print("no matches.", file=sys.stderr)
        return 1

    fused = rrf_fuse(rankings, args.rrf_k) if rankings else []
    
    # Apply sorting if requested (overrides RRF ranking)
    if args.sort or args.sortr:
        sort_field = args.sortr if args.sortr else args.sort
        reverse = bool(args.sortr) or args.reverse
        paths = [p for p, _, _ in fused]
        sorted_paths = sort_files(paths, sort_field, reverse, args.dirs_first, args.dirs_last)
        # Rebuild fused with sorted order but preserve scores and labels
        path_to_data = {p: (s, l) for p, s, l in fused}
        fused = [(p, path_to_data[p][0], path_to_data[p][1]) for p in sorted_paths if p in path_to_data]
    elif args.dirs_first or args.dirs_last:
        # Apply directory grouping even without explicit sorting
        paths = [p for p, _, _ in fused]
        sorted_paths = sort_files(paths, None, False, args.dirs_first, args.dirs_last)
        path_to_data = {p: (s, l) for p, s, l in fused}
        fused = [(p, path_to_data[p][0], path_to_data[p][1]) for p in sorted_paths if p in path_to_data]
    
    render(fused, name_scores, content_hits, git_cache, args, use_color, query_pattern=pattern)

    # Brain Recall
    if brain_recall and not args.files_only:
        print(f"\n{c('35', '🧠 brain recall (semantic — memory chunks, not files):', use_color)}")
        for hit in brain_recall:
            print(f"    {c('90', '·', use_color)} {hit['snippet']}")

    # Search Stats
    if args.stats:
        elapsed = time.time() - start_time
        total_hits = sum(d.get("count", 0) for d in content_hits.values())
        print(f"\n{c('1;37', 'Search Statistics:', use_color)}", file=sys.stderr)
        print(f"  Duration:          {elapsed:.3f}s", file=sys.stderr)
        print(f"  Files with hits:   {len(content_hits)}", file=sys.stderr)
        print(f"  Total match count: {total_hits}", file=sys.stderr)
        print(f"  Engine:            {'ripgrep 15.2.0 (SIMD/mmap)' if HAVE_RG else 'pure-Python (fallback)'}", file=sys.stderr)

    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
