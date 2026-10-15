## Agent skills

### Issue tracker

Tickets are GitHub issues (use `gh`); specs and the finished architecture map stay as markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default triage labels, unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Branches

Each ticket is implemented on its own branch, named `issue-<number>-<short-slug>` (for example `issue-1-walking-skeleton`) and created from `main` before any changes. Never commit ticket work to `main`.
