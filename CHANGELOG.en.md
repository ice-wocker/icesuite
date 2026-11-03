# Changelog

Every change to this repository, newest first. Version numbers track deployment;
build artifacts are not committed.

## 2026-11-03 · v3 "final"

The previous release moved "bumping a version means pushing code" and
"a new project can only be added after the fact" into the pipeline.
This one goes one step further on the same idea: **make "how much is there,
is it accurate, and does it work offline" questions the pipeline can answer.**

The trade-off in one line: **no new feature buttons — only new verifiable exits.**

### 1. Five new pages

| Page | Question it answers | Source |
|---|---|---|
| `latest.html` | What is new? | Every release by `published_at`, grouped by date |
| `timeline.html` | How many releases, at what rhythm? | Same data as a year/month column chart |
| `compare.html` | How do similar projects differ? | Only groups with >= 2 projects |
| `collections.html` | What is there by theme? | 10 collections, all computed; the rule is printed on the page |
| `stats.html` | Why should I believe these numbers? | A typeset view of `stats.json` |

None of these is "the same content in another layout": `latest` used to require
opening every project page, `timeline` flattens release notes into history for the
first time, `compare` used to mean four browser tabs and your own memory.

### 2. Four machine-readable artifacts

| File | For whom |
|---|---|
| `update.json` (existing, extended) | Update checks inside the apps; new top-level `verify` self-report |
| `stats.json` (new) | Anyone who wants to check the site's numbers |
| `graph.json` (new) | Nodes = projects, edges = same group or shared tag. **No behavioural data.** |
| `content.json` (new) | Per-file sha256 + byte count + build fingerprint |

Field semantics: [docs/CONTRACTS.md](docs/CONTRACTS.md).

### 3. Installable and offline-capable (PWA)

`manifest.json` + `sw.js` + a maskable icon. Three hard rules:

1. **Network first, cache second.** Cache-first means a user who installs the app
   never sees a new version again and cannot self-heal.
2. **Same-origin GET only.** GitHub's 302 chain and mirror prefixes stay out of the
   cache — freezing them there only makes people think the site is broken.
3. **A failed Service Worker registration must not affect the main function.**
   `file://`, private mode and some WebViews all refuse it, and none of the core
   features need it.

The cache name carries the build fingerprint. **APKs cannot be downloaded offline** —
they are cross-origin and CORS does not let a service worker read the response body.
The page says so instead of faking certainty.

Details: [docs/PWA.md](docs/PWA.md).

### 4. Two new blocks on project pages

- **Health**: what state the project is in, stated as verifiable facts (days since
  the last release, whether an artifact exists, whether a licence exists, download
  count). No score, no recommendation. Every row tells you how to check it yourself.
- **Related projects**: ordered by shared tags, then same group, then name —
  the same input always yields the same order, so builds stay reproducible.
  When there are no neighbours it says so explicitly rather than leaving a gap.

### 5. Guards: 15 -> 44, and four of the new ones were rubber stamps

New `scripts/mutate_v2.py` (29 cases): inject a defect, require the self-check to go
red, **and require it to go red for the expected reason**. It caught four fake guards
immediately:

| Rubber stamp | What it was hiding |
|---|---|
| "Related projects exist" searched the whole site for a word | Delete the block from 20 of 21 pages and it stays green |
| "Collections have cards" counted `.cardhit` site-wide | One empty collection plus one over-rendered one keeps the total |
| "Home links to stats.html" searched the whole page | The footer link kept it green after the entry block was deleted |
| The mutation test itself: page edits were caught by the content.json guard first | A batch of new guards was never actually tested |

The last one matters most: **a mutation test can become a rubber stamp too.** Every
page-mutating case now refreshes that file's hash in `content.json` first.

The `guards` job also ends with a **reverse self-check**: corrupt one artifact and
confirm `check_site` really goes red. Otherwise, if `check_site` ever returns 0
unconditionally, both mutation suites pass together — a double failure that looks green.

### 6. Five bugs this release introduced itself (all now guarded)

| Bug | Symptom | Guard |
|---|---|---|
| `SEARCH_JS` was a plain string, so `\\` collapsed to `\` | A character-class regex closed early, the whole script failed to parse: you could type in the box and never get a result | `scripts/js_syntax.py` runs `node --check` on every inline script |
| Page-specific scripts placed in `<head>` | Sortable table headers did nothing (DOM not parsed yet) | Found by clicking in a browser; noted here because static checks passed |
| `content.json` written before the PWA files | The index omitted `manifest.json`, `sw.js`, `CNAME` | Assertion: no unlisted artifacts on disk |
| `update.json`'s `generated_at` used build time | Two identical builds produced different files | `check_site --reproducible` byte-compares two builds |
| Compare table used `table-layout:auto` | Horizontal overflow at 390px; the project name got pushed off-screen | `fixed` layout with computed column widths; two columns hidden on narrow screens |

### 7. New scripts

```text
scripts/overlay.py      the only merge implementation (shared by build and check)
scripts/insight.py      derived data: stats, timeline, collections, health
scripts/pages.py        renderers for the five new pages
scripts/app_assets.py   manifest / service worker / icons
scripts/util.py         shared helpers (escaping, dates, structural hash)
scripts/js_syntax.py    node --check for inline JavaScript
scripts/mutate_v2.py    29 mutation cases for the new guards
scripts/live_check.py   verify the deployed site: fingerprint, update.json, sampled APK sha256
```

### 8. How far verification went

```text
build_site.py              22 projects / 12 installable / 31 pages / 45 artifacts / 665 KB
check_site.py              all green (including 38 external HEAD requests)
check_site --reproducible  two builds byte-identical
mutate_test.py             15/15 self-verified
mutate_v2.py               29/29 self-verified
js_syntax.py               130 inline scripts parse
headless browser           10 pages at 390px with no horizontal overflow; two header
                           clicks really do reorder the table; search "推理" returns 3
                           and "本地推理" returns 1; service worker registers
live                       live_check.py runs in CI after deploy
```

### 9. Still not done

- **Comments / ratings**: needs a backend, abuse handling and GDPR work, and it
  contradicts "zero dependencies, no tracking, no cookies".
- **Auto-generated descriptions**: machine text reads like "a great app with
  excellent performance" and everyone can tell.
- **Offline APK downloads**: CORS does not allow it. Not doing it is the honest answer.
- **Guessing `versionCode` or sha256**: absent means `null`.
- **Safari / Firefox testing**: only Chromium was checked page by page. The `hidden`
  attribute and `:target` are the two most likely to differ on older Safari.

