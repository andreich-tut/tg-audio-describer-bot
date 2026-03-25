---
name: commit-name
description: Suggest a git commit message for current changes without committing. Use when user asks for a commit name/message.
allowed-tools: [Bash]
---

# commit-name

Suggest a conventional commit message for the current changes. Do NOT run `git commit`.

## Steps

1. Run `git diff --staged`. If empty, run `git diff HEAD`. If still empty, run `git status`.
2. Analyze what the changes actually do — their intent, not just which files changed.
3. Output a single commit message in Conventional Commits format:
   `<type>(<optional scope>): <short description>`
   - Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`, `style`
     - `feat` — new feature for the user
     - `fix` — bug fix
     - `chore` — maintenance task (build, deps, tooling); no production logic change
     - `docs` — documentation only
     - `refactor` — code restructuring without behavior change
     - `test` — adding or updating tests
     - `ci` — CI/CD pipeline changes
     - `style` — formatting, whitespace, semicolons (no logic change)
   - Description: imperative mood, lowercase, no period, max ~72 chars

## Output

Print only the commit message string. No explanation, no quotes, no extra text.
