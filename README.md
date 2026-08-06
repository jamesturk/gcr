# gcr

Command-line utility for running a class on GitHub, a lightweight GitHub classroom replacement.

At the moment, this is early alpha software, use at your own risk.

*Feedback welcome!*

## Installation

The recommended method for installation is `uv tool install gcr-cli`, you can then run `gcr`.

uvx: `uvx --from gcr-cli gcr`

pipx: `pipx install gcr-cli`, then run `gcr`

## Setup

1. Set env variable GITHUB_TOKEN to a classic token with org & repo admin permissions.
1. Manually create a GitHub organization for your classroom.
1. Create a `class.toml` with your roster & settings. `gcr` will look for `class.toml` in the current directory, or you can pass the `-c/--config` option to specify the path.

```toml
org = "name-of-github-org"

students = [
  "list",
  "of",
  "student",
  "accounts",
]

staff = [
  "list",
  "of",
  "staff",
  "accounts",
]

staff_team = "staff"
student_team = "students"
student_permission = "push"
staff_permission = "maintain"
requests_per_minute = 60
retry_attempts = 3
retry_wait_seconds = 5
```

## Usage

All commands take two options:

- `-c`/`--config`: path to `class.toml` (default: current dir)
- `--dry-run`: avoid making actual changes on GitHub

### `gcr setup`

Initialize GitHub organization and invite staff & students.

*The organization must already exist and your API key must have access.*

### `gcr assign {template-repo-name}`

Creates one private repo per student, granting access to their account & staff.

### `gcr clone {assignment} [optional-student]`

Clone student repos to a local directory.

## Changelog

### 0.3.0 - 5 August 2026

- Addition of `clone`
- Prompt to automatically make assignment repository a template.

### 0.2.0 - 4 August 2026

- First 'public' release.
