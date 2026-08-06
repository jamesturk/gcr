

## Setup

1. Set env variable GITHUB_TOKEN to a classic token with org & repo admin permissions.
2. Create a class.toml with roster & settings.

### class.toml

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

## Usage

### Initialize

`gh-class setup`

Initialize GitHub organization and invite staff & students.

*The organization must already exist and your API key must have access.*

### Create Assignment

`gh-class assign <template-repo-name>`

Creates one private repo per student, granting access to their account & staff.
