# Contributing

> [中文版](CONTRIBUTING.md)

## Current Project Status

rwrsb is in **maintenance mode**: the core features (skeleton binding editing, animation tool, packaged releases) are essentially complete. Future work will mainly consist of bug fixes and small improvements. New feature requests may arise when RWR2 launches — feel free to open an issue to discuss.

There are no automated tests — all changes rely on manual verification.

## Reporting Bugs

Please open an issue on GitHub. Describe the problem in the title (e.g., "Crash when importing a VOX file with a Chinese path").

**Including the following information makes the issue much easier to diagnose:**

- The most recent log file from the `logs/` directory (typically at `dist\rwrsb_bind\logs\` or `%LOCALAPPDATA%\rwrsb_gui\logs\`)
- Steps to reproduce (what file you used, what you did, what happened)
- Your OS version and Python version (if running from source)

## Suggesting Features

Feature suggestions are best discussed first in the **RWR mod community group** by pinging SAIWA, then tracked in a GitHub issue once the direction is confirmed. This avoids getting halfway through an implementation only to find the direction is wrong.

Small improvements that you are unsure about can also be filed directly as issues without writing any code first.

## Submitting a Pull Request

1. Fork the repository and run `setup.bat` locally to initialize the environment.
2. Create a branch from `main`, named like `feat/xxx` or `fix/xxx`.
3. Make your changes — **do not introduce new third-party dependencies**.
4. Use [Conventional Commits](https://www.conventionalcommits.org/) style:
   - `feat: add feature`
   - `fix: bug fix`
   - `docs: documentation change`
   - `refactor: refactor (no behavior change)`
5. In the PR description, explain: **what changed**, **how you verified it manually**, and **whether it affects the XML import/export format**.

When changing skeleton logic or coordinate transformations, pay special attention to verifying: viewport dragging, panel editing, preset save/load, undo/redo, XML export, and binding remap after stick deletion. These paths are the most likely to interfere with each other.

## Testing Notes

This project has **no automated tests**. After making changes, please follow the "pre-release checklist" in [RELEASE_EN.md](RELEASE_EN.md) and manually run through the main features to confirm there are no regressions.
