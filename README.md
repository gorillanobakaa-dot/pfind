# pfind

<!-- WHO-THIS-IS-FOR: managed block, do not edit by hand -->

**Find a file by name, content, meaning, or an exact code snippet. One Python file, no index and no database to build.**

Built for the people every other tool prices out: kids with no credit
card, 15-year-old laptops, data sold by the megabyte. Free forever, by
design, not as a trial.
Why, with the numbers: [PHILOSOPHY.md](https://github.com/gorillanobakaa-dot/Gorilla.Opencode/blob/main/PHILOSOPHY.md)

<!-- /WHO-THIS-IS-FOR -->

**One command to find anything on your machine** — by filename, by what's *inside* the
files, by *meaning*, or by an exact chunk of code you half-remember — with the results
**ranked** so the few that matter show up first.

It's a single Python file. Under the hood it drives [ripgrep](https://github.com/BurntSushi/ripgrep)
(fast, battle-tested search) and adds a brain on top: multi-signal search, relevance ranking,
exact multi-line snippet matching, and optional semantic search over a local vector database.

> Built and tested against a real ~120-million-line, 1.3-million-file working tree. If every
> index and database on the machine vanished tomorrow, pfind + your raw files is still enough
> to find any needle again.

---

## Table of contents

1. [The 30-second version](#1-the-30-second-version)
2. [The problem it solves (a short story)](#2-the-problem-it-solves-a-short-story)
3. [Install](#3-install)
4. [Making it a real command — the `alias` lesson](#4-making-it-a-real-command--the-alias-lesson) ⭐
5. [The five ways to search](#5-the-five-ways-to-search)
6. [How to read the results](#6-how-to-read-the-results)
7. [How the ranking works (in plain English)](#7-how-the-ranking-works-in-plain-english)
8. [Full command reference](#8-full-command-reference)
9. [Turning a fuzzy idea into search terms](#9-turning-a-fuzzy-idea-into-search-terms)
10. [Worked example: a messy real-world prompt](#10-worked-example-a-messy-real-world-prompt)
11. [Honest limits & when *not* to use it](#11-honest-limits--when-not-to-use-it)
12. [Under the hood](#12-under-the-hood)
13. [Adapting pfind to *your* machine](#13-adapting-pfind-to-your-machine)
14. [For AI agents landing with zero context](#14-for-ai-agents-landing-with-zero-context)
15. [Contributing & versioning discipline](#15-contributing--versioning-discipline)

---

## 1. The 30-second version

```bash
python3 pfind.py <what-you-want> [where-to-look] [options]
```

```bash
# find a file whose name you half-remember
python3 pfind.py orchestr --fuzzy

# find whatever file CONTAINS this thing (even if the file was renamed)
python3 pfind.py run_gpu_liberator

# find an exact block of code you remember, anywhere
python3 pfind.py "kmemleak_alloc(s, size, 1, GFP_KERNEL);
	memset(s, 0, sizeof(*s));" --exact
```

If you set up the [alias](#4-making-it-a-real-command--the-alias-lesson), every command
above becomes just `pfind …`.

---

## 2. The problem it solves (a short story)

There are three completely different ways to look for something, and most tools only do one:

- **By exact words** — "the file that literally says `MOZ_APP_REMOTINGNAME`." This is what
  `grep` does. It's perfect when you know the exact text and useless when you don't.
- **By meaning** — "the note about *why the window goes black*." You don't remember the words,
  just the idea. This is what a search engine or a vector database does.
- **By filename** — "there's a script called something like *deploy*." This is what `ls *.sh`
  or a file-finder does.

The pain shows up the moment you need **more than one at once**. A real example that inspired
this tool: a file called `setup_orchestrator.py` got renamed to `build.py` by an automated
process. Searching by *filename* for "orchestrator" found nothing. The thing we actually
remembered — that it contained a function called `run_gpu_liberator` — was *inside* the file.
A filename search will never find that. You need to search names **and** contents at the same
time, and see the answer ranked at the top.

That's pfind: it runs several kinds of search together, merges them fairly, and hands you a
short ranked list instead of 400 raw matches.

---

## 3. Install

**Requirements:**

| Thing | Why | Notes |
|---|---|---|
| **Python 3** | pfind is a Python script | 3.8+; tested on 3.13. Standard library only for the core. |
| **ripgrep** (`rg`) | the actual search engine | Strongly recommended. Without it, pfind falls back to a slower pure-Python search. [Install guide](https://github.com/BurntSushi/ripgrep#installation). |
| **chromadb** *(optional)* | only for `--brain` semantic search | `pip install chromadb`. Skip it if you don't use semantic search. |

**Get it:**
```bash
git clone https://github.com/gorillanobakaa-dot/pfind.git
cd pfind
python3 pfind.py --help
```

That's it — there's nothing to build.

---

## 4. Making it a real command — the `alias` lesson ⭐

Typing `python3 /long/path/to/pfind.py` every time is miserable. Let's make it just `pfind`.
If you already know what a shell alias is, skip to the [command](#the-command). If not, read on —
this is a genuinely useful thing to understand.

### What is an alias?

An **alias** is a nickname for a longer command. When you type the nickname, your shell (the
program that reads what you type in the terminal — usually **bash** or **zsh**) silently
replaces it with the full command before running it. So:

```bash
alias pfind='python3 /home/you/Documents/pfind/pfind.py'
```

...means "whenever I type `pfind`, actually run `python3 /home/you/Documents/pfind/pfind.py`."
Type `pfind orchestr --fuzzy` and the shell expands it to
`python3 /home/you/Documents/pfind/pfind.py orchestr --fuzzy`. You get the short word; the
computer gets the full command.

### Why put it in a file?

If you just type that `alias …` line into your terminal, it works — **until you close the
window.** Aliases live only in the terminal session that created them. To make it permanent,
you write it into your shell's **startup file** — a script your shell runs automatically every
time a new terminal opens. On bash that file is `~/.bashrc` (the `~` means your home folder).
Every new terminal reads `~/.bashrc`, sees the alias, and sets it up for you. On zsh it's
`~/.zshrc`.

### The command

Pick the block for your shell. This appends the alias to your startup file. **Adjust the path**
if you cloned pfind somewhere other than `~/Documents/pfind`.

**bash:**
```bash
echo "alias pfind='python3 ~/Documents/pfind/pfind.py'" >> ~/.bashrc
```

**zsh:**
```bash
echo "alias pfind='python3 ~/Documents/pfind/pfind.py'" >> ~/.zshrc
```

### Turn it on

Your *current* terminal was opened before you added the alias, so it doesn't know about it yet.
Either open a brand-new terminal, or reload the startup file into this one:

```bash
source ~/.bashrc      # or: source ~/.zshrc
```

`source` means "run this file's commands right now, in the terminal I'm sitting in."

### Check it worked

```bash
pfind --help
```

If you see pfind's help, you're done. From now on, in any new terminal, `pfind` just works.

### If it doesn't work

- **"command not found: pfind"** — the startup file wasn't reloaded. Open a new terminal, or
  run `source ~/.bashrc` again. Double-check the path in the alias points at the real
  `pfind.py`.
- **Wrong shell?** Run `echo $SHELL`. If it says `/bin/zsh`, put the alias in `~/.zshrc`, not
  `~/.bashrc`.
- **The alias runs but Python errors** — the path in the alias is wrong. Run the full
  `python3 /the/path/pfind.py --help` by hand to find the correct path, then fix the alias.

### To remove it

Open `~/.bashrc` (or `~/.zshrc`) in any text editor, delete the `alias pfind=…` line, save,
and open a new terminal. Nothing else to clean up — an alias is just one line of text.

> **Tip:** wrap the line in comment markers so future-you knows what it is and where the docs
> are — this is exactly how this project's own machine has it set up:
> ```bash
> # >>> pfind (search tool — docs: ~/Documents/pfind/README.md) >>>
> alias pfind='python3 ~/Documents/pfind/pfind.py'
> # <<< pfind <<<
> ```

**From here on, this README writes commands as `pfind …`** assuming you set up the alias.
No alias? Just use `python3 pfind.py …` instead.

---

## 5. The five ways to search

### Mode 1 — by filename
> "There's a file called roughly *deploy*."

```bash
pfind deploy                     # names + contents, ranked
pfind deploy --names             # names only
pfind orchestr --names --fuzzy   # tolerates typos/partials → finds setup_orchestrator.py
pfind 'deploy.*\.sh$' --names -r # regex on the name
```

### Mode 2 — by content (what's *inside*)
> "I don't remember the filename, but it had `run_gpu_liberator` in it."

This is the one that survives a file being **renamed**.
```bash
pfind run_gpu_liberator          # finds the file whose contents mention it
pfind "VA-API" --content -i      # case-insensitive content search
```

### Mode 3 — by meaning (semantic / `--brain`)
> "I remember what it was *about*, not the exact words."

This searches a local vector database (a "second brain") by *meaning*, and fuses those hits
with the literal ones.
```bash
pfind "how do we stop the black window on wayland" --brain
pfind "vertical tabs performance" --brain
```
Semantic search is a **recall booster, not gospel** — it can wander to false friends (a
"black window" query once drifted into unrelated "AppWindow" docs). Use it to *surface*
candidates, then read them to confirm.

### Mode 4 — by exact code snippet ⭐ (the headline feature)
> "Find me *this exact code*, wherever it is."

Paste the block verbatim — newlines and all. pfind matches it **literally, across lines**.
```bash
pfind "kmemleak_alloc(s, size, 1, GFP_KERNEL);
	memset(s, 0, sizeof(*s));" --exact
```
Half-remember the spacing/indentation? Add `--loose` to tolerate whitespace drift (tabs vs
spaces, extra blank lines):
```bash
pfind "kmemleak_alloc(s, size, 1, GFP_KERNEL); memset(s, 0, sizeof(*s));" --loose
```
*Measured on the reference machine (SSD):* an exact 2-line snippet across ~120 M lines /
1.34 M files → **~70 seconds cold**, seconds warm. No index, no database.

### Mode 5 — plain filename globbing (and when *not* to use pfind)
If you already know the exact pattern, the simple tools are faster and cleaner:
```bash
ls *.sh                          # you know exactly what you want
rg --files | rg pattern          # a raw, complete, unranked list
rg 'literal string'              # raw content matches to pipe elsewhere
```
**Rule of thumb:** *know exactly what you want → simple tool. Half-remember it, or don't know
where it lives → pfind.*

---

## 6. How to read the results

```
0.0328  [name,6 hits]  /home/you/Documents/pfind/pfind.py
    14: # ...the matching line...
```

- **`0.0328`** — a relevance score. Bigger = more relevant. Results are sorted by it.
- **`[name,6 hits]`** — *why* this result ranked where it did:
  - `name` — the filename matched your query
  - `6 hits` — the file's contents matched 6 times
  - `semantic` — a meaning-based (brain) match
- **the path**, then a few indented `line-number: text` samples.
- Multi-line snippet matches are folded onto one line with a **`↵`** marking each line break.
- Meaning-based memories that aren't tied to a file print in a separate **🧠 brain recall**
  block at the end — they're remembered *ideas*, not files.

The `[why]` tags are the point: you never have to guess why something showed up.

---

## 7. How the ranking works (in plain English)

Two ideas, both aimed at one goal: **put the actually-relevant file first.**

**1. Coverage beats volume.** Imagine you search for a concept using several related words at
once (say `regdomain`, `channel 14`, `unlock`). One file mentions the phrase "all channels"
200 times but nothing else. Another file mentions `regdomain` *and* `channel 14` *and*
`unlock` just once each. The second file is far more likely to be your answer — it covers more
of what you asked. pfind ranks by **how many distinct query-terms a file matches**, not by raw
hit-count. A one-line config can beat a 200-hit source file.

**2. Different signals get different weight.** A filename match is a stronger hint than "this
word appears in the text a lot," so pfind weights name matches and semantic matches above plain
content matches when merging the lists. The merging math is
**[Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormack/cormacksigir09-rrf.pdf) (RRF)** —
a standard, robust way to combine several ranked lists without their scores having to be on the
same scale. (Knob: `--rrf-k`, default 60; lower values sharpen small result sets.)

---

## 8. Full command reference

```
pfind QUERY [ROOTS...] [FLAGS]
```
`QUERY` — what to find. **Literal text by default** (safe for code full of `(){}*.`); use
`-r` for regex. `ROOTS` — where to look; defaults to the current directory (or a preset).

### Where to search (presets)
These are convenience shortcuts to the reference machine's folders. **[Edit them for your own
machine](#13-adapting-pfind-to-your-machine).**

| Flag | Searches |
|---|---|
| `--brain` | the Second Brain folder **and** turns on semantic search |
| `--work` | the working/project folder |
| `--src` | the source-code tree |
| `--all` | all three at once |
| *(none)* | current directory, or the ROOTS you name |

### What to match
| Flag | Effect |
|---|---|
| *(default)* | filename **and** content, fused + ranked |
| `--names` | filenames only |
| `--content` | contents only |
| `-r`, `--regex` | treat QUERY as a regular expression |
| `-i`, `--ignore-case` | force case-insensitive (default is *smart-case*) |
| `--fuzzy` | typo/partial-tolerant filename matching |
| `-x`, `--exact` | exact multi-line snippet (literal, spans newlines) |
| `--loose` | snippet match tolerant of whitespace/indent drift |

### Scope filters
| Flag | Effect |
|---|---|
| `--ext .py .sh` | only these extensions |
| `--exclude GLOB…` | extra names/globs to skip |
| `--hidden` | include dotfiles |
| `--no-ignore` | ignore `.gitignore` rules |

### Tuning & output
| Flag | Default | Effect |
|---|---|---|
| `--workers N` | CPU count | search threads |
| `--timeout S` | 600 | give-up time for the content search |
| `--rrf-k N` | 60 | rank-fusion constant |
| `--max N` | 5 | sample lines shown per file |
| `--limit N` | 40 | max files shown (`0` = all) |
| `--collection NAME` | `core_memory` | which brain collection `--brain` queries |
| `--files-only` | | print paths only (script-friendly) |
| `--count` | | print a match-count summary |
| `--no-color` | | disable coloured output |

**Always-on noise excludes:** version-control dirs, `node_modules`, `__pycache__`, build/object
dirs (`obj-*`, `dist`, `build`, `.mozbuild`), Python/virtualenv caches, vector-store binaries
(`chroma_db`, `*.sqlite3`, `*.bin`, `*.parquet`), and minified assets. ripgrep also honours
`.gitignore` unless you pass `--no-ignore`.

**Exit codes:** `0` = ran, `1` = no matches, `130` = interrupted.

---

## 9. Turning a fuzzy idea into search terms

pfind's content/snippet search is **literal** — it needs words that are actually in the files.
So translate a vague concept into the specific terms it lives under, then OR them together with
`-r`:

| You remember… | Try searching |
|---|---|
| "make wifi work on every channel" | `regdom\|REGDOMAIN\|ieee80211_regdom\|iw reg set\|wireless-regdb\|CRDA\|channel 14` |
| "the setting that turns off telemetry" | `telemetry\|MOZ_TELEMETRY\|data.?report\|glean` |
| "where the icon/branding gets set" | `rebrand\|branding\|icon\|RemotingName` |

Don't know the terms at all? Run it with `--brain` first — let semantic search surface the
vocabulary, then re-search literally for precision.

---

## 10. Worked example: a messy real-world prompt

Real requests are rarely clean. Here's a deliberately chaotic one, and how to handle it:

> *"yo find me this `kmemleak_alloc(s, size, 1, GFP_KERNEL); memset(s, 0, sizeof(*s));` and
> fix whatever's wrong and make it work, etc etc etc"*

Step by step:

1. **Spot the real request.** The payload is an exact code fragment → this is a **snippet
   search**. The filler ("yo", "etc etc") carries no search signal — ignore it.
   ```bash
   pfind "kmemleak_alloc(s, size, 1, GFP_KERNEL); memset(s, 0, sizeof(*s));" --all --loose
   ```
   (`--loose` because the pasted spacing may not match the file's real indentation.)
2. **Read the result.** pfind points you at the exact `file:line`. Open it and read the
   surrounding code.
3. **Don't invent a bug.** "Fix whatever's wrong" assumes something *is* wrong. Maybe nothing
   is. **pfind locates; it does not edit.** Confirm the actual symptom, read the file (and any
   project rules), and only then make a deliberate change.
4. **Ignore the noise.** "make it work / etc etc" state no concrete requirement — don't act on
   filler.

The lesson: **pfind gets you to the right line fast and reliably; judgement and edits are a
separate, deliberate step.**

---

## 11. Honest limits & when *not* to use it

- pfind is **never faster than raw ripgrep** — it trades a little speed for ranking, meaning,
  and multi-line snippets. Need a raw list to pipe? Use `rg` directly.
- `--loose` tolerates *added/changed* whitespace, not *removed* whitespace — it needs some
  whitespace between tokens. If a snippet had its spaces stripped, use `--exact` or shorten the
  query to one distinctive line.
- Snippet mode is **content-only** — a pasted code block is never treated as a filename.
- The pure-Python fallback (when `rg` is missing) is correct but slow; don't run it over a huge
  tree.
- It builds **no persistent index** — see below for why that's a deliberate choice.

---

## 12. Under the hood

- **Engine:** pfind shells out to **ripgrep** — it enumerates files (`rg --files`) and searches
  contents (`rg --json`), then does the ranking/fusion in Python. If `rg` is missing it falls
  back to a pure-Python walker so it never hard-fails.
- **Exact snippets:** ripgrep's multi-line mode (`-U`) with fixed-string matching (`-F`).
  `--loose` compiles your snippet into a whitespace-flexible regex.
- **Semantic search:** an optional query against a local [Chroma](https://www.trychroma.com/)
  vector database, using the `all-MiniLM-L6-v2` embedding model. It degrades gracefully — if
  the DB or model isn't there, pfind just skips semantic and does the rest.
- **No index, by design.** A pre-built search index makes repeat queries instant, but it goes
  stale, needs rebuilding, and is one more thing that can be lost or corrupted. On an SSD, a
  full scan of even a 120 M-line tree is about a minute cold and seconds warm — cheap enough
  that the raw files themselves *are* the index. That keeps pfind dependable precisely when
  everything else is gone. (If you truly need instant repeat-search over a huge, stable tree,
  a trigram indexer like `ugrep-indexer` or Google's `csearch` is the upgrade path.)

---

## 13. Adapting pfind to *your* machine

This copy is tuned for one specific laptop. To make it yours, open `pfind.py` and edit the
constants near the top:

- **`PRESET_ROOTS`** — the folders behind `--brain` / `--work` / `--src`. Point these at *your*
  projects (or delete the ones you don't want).
- **`BRAIN_CHROMA` / `BRAIN_DEFAULT_COLLECTION`** — path to your Chroma database and the default
  collection name, if you use `--brain`.
- **`MACHINE` / `LOGICAL_CPUS`** — cosmetic label and the default thread count.
- **`EXCLUDE_GLOBS`** — the always-skip noise list; add anything specific to your trees.

Everything else works out of the box.

---

## 14. For AI agents landing with zero context

If you are an automated agent asked to find something here, don't hand-roll `grep`. Use pfind.
Pick the mode by the shape of the request:

```
Exact code/text fragment (punctuation, braces, or newlines)?  → --exact  (+ --loose if spacing is uncertain)
Know a filename or part/typo of one?                          → default or --names  (+ --fuzzy)
Describe a concept, not exact words?                          → translate to literal terms, OR with -r  (+ --brain if it's about stored knowledge)
Don't know where it lives?                                    → add --all  (or scope to one preset to go faster)
```

Then **read the top hit before doing anything else** — pfind returns `path:line`, not answers.
**Hard boundary: pfind LOCATES, it does not EDIT.** "Find X and fix it" ends, for pfind, at the
file and line; any fix is a separate, deliberate step that reads the file and the project's
rules first. Never assume something is broken just because you were told so.

---

## 15. Contributing & versioning discipline

`pfind.py` carries a header: `# VERSION | UPDATED | STATUS` and a `# CHANGELOG`.

**To change the tool: edit the file, bump the version, add a changelog line.** Do **not** create
`pfind_v2.py` / `pfind_new.py` / a renamed copy — spawning duplicates instead of editing is the
exact mess this kind of tool exists to clean up. One canonical file, versioned in place.

Current: **v2.1.0** — hybrid name+content+fuzzy search, RRF fusion, exact/loose multi-line
snippet search, coverage ranking, and an optional semantic layer over a local vector database.

---

## License — GNU AGPL-3.0-or-later

pfind is **free and open source** under the [GNU Affero General Public License v3](LICENSE).
In plain English:

- ✅ **Use it, fork it, modify it, sell it, embed it** — do whatever you want with it.
- 🔁 **One condition (copyleft):** if you distribute a modified version — *or run a modified
  version as a network/hosted service* — you must make **your** source available under this
  same license. Improvements can never be locked away in a closed fork; they stay open, so the
  tool keeps growing and anyone can pull them back in.
- ❗ **Honest note:** the license doesn't *force* you to send patches upstream — it just
  guarantees your changes stay open if you ship or host them. Sending them back is encouraged,
  not compelled. That's how a project "takes on a life of its own."

The AGPL (rather than plain GPL) is deliberate: it closes the "runs it as a service without
sharing" loophole, which matters because pfind has a plausible server future (semantic search,
tool servers). If you build pfind into a networked service, honor AGPL §13 — offer your users
the corresponding source.

*Privacy:* pfind is local by default and sends nothing over the network. The only exception is
the optional `--brain` semantic model, downloaded once from Hugging Face, after which it runs
entirely offline.
