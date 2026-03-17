# Session — 2026-03-17 (afternoon)

## What we did
- Confirmed PS1 custom prompt didn't work — escape sequences were rendering literally in SSH terminal
- Removed the custom PS1 line from `.bashrc`, reverted to default prompt
- Created `session-saves/` folder in `~/projects/cc-unhinged-repo/`
- Designed and documented a session save strategy (naming convention, sections, trigger shortcut)
- Pushed folder + README to GitHub
- Updated Claude memory to reflect new save target and workflow

## Decisions made
- PS1 customization abandoned for now — CC terminal and SSH terminal behave differently enough to make it more trouble than it's worth
- Session saves live in the GitHub repo at `session-saves/YYYY-MM-DD-slug.md`
- Trigger: `save:"slug"` — Claude writes, commits, pushes automatically
- Save format: What we did · Decisions made · Open threads · Next up

## Open threads
- 11 projects still pending (Self-Modifying Agent Sandbox is top priority)
- Conversation history search idea from last session not yet acted on
- `.bashrc` backup at `~/.bashrc.bak-2026-03-17` if anything needs reverting

## Next up
- Start on Project #9 — Self-Modifying Agent Sandbox
- Continue building out the repo with project work
