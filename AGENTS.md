# Agent Instructions for `bibcanon`

Welcome to the **`bibcanon`** workspace!

## Primary Specification
Before writing any code, **read [SPEC.md](./SPEC.md) in its entirety**. `SPEC.md` is the finalized single source of truth for product scope, data models, external API contracts, publisher adapters, field retention policies, REST/SSE APIs, frontend UI design, and phased acceptance criteria.

## Key Scope & Product Decisions (Do Not Over-Engineer)
1. **Single `.bib` Full-File Workflow Only**: Support pasting/uploading a single `.bib` file or passing a local `.bib` path. Do **not** build `.tex` / `.bbl` / `.aux` / `.zip` multi-file citation scanners.
2. **Standard CLI Launch Only**: Provide the `bibcanon` CLI (`serve`, `check`, `fix`, `cache`). Do **not** add `.bat` wrapper scripts or desktop app shells.
3. **Publisher-Verbatim Default (`canonical` mode)**: Keep **all** authentic publisher-provided fields (`url`, `doi`, `month`, `publisher`, `organization`, `address`, `editor`, `volume`, `number`, `series`, `pages`, `articleno`, `numpages`, `pdf`, `isbn`, `issn`, etc.), stripping **only** reference-manager/aggregator noise (`abstract`, `file`, `local-url`, `mendeley-tags`, `zotero-key`, `annote`, `biburl`, `bibsource`, `timestamp`).
4. **arXiv Native `@misc` Format**: Unpublished arXiv preprints must use arXiv's official `@misc` format (`eprint`, `archivePrefix = {arXiv}`, `primaryClass`, `url`).
5. **Respect Original Venue Intent**: If the original `.bib` entry already names a valid published venue (e.g., `CVPR`), default `candidates[0]` to that venue's official publisher BibTeX and list any subsequent journal extension (e.g., `TPAMI`) as `candidates[1]`. Auto-upgrade to the highest-tier published version only when the original entry is a preprint (`arXiv` / `CoRR`).

## Execution Rules & Golden Invariants
1. **Follow Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5** in Section 8 of `SPEC.md`, running and passing `pytest` (and `tsc --noEmit` + `vite build` in Phase 5) at the end of every phase.
2. **Preserve Citation Keys**: Never alter the original `cite_key` unless explicitly edited by the user.
3. **Lossless `.bib` Patching**: Untouched entries, `@string` macros, `@preamble`, and `%` comments must remain byte-for-byte intact via character-span splicing. Always create a timestamped `.bak` backup before overwriting any local `.bib` file.
4. **Network Errors != Hallucinations**: Upstream timeouts or offline states must map to `ERROR`, never `SUSPECTED_HALLUCINATION`.
5. **Windows & Proxy Compatibility**: Always pass `encoding="utf-8"` to all file operations, use `pathlib.Path`, and initialize `httpx.AsyncClient(trust_env=True, follow_redirects=True)` (plus optional `proxy_url` from settings).
6. **No Anti-Bot Scraping**: Never scrape Google Scholar, Bing, or bot-gated commercial publisher HTML pages directly.
