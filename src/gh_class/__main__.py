"""
gh-class: minimal GitHub classroom replacement CLI

## Setup

1. Set GITHUB_TOKEN to a classic token with org & repo admin permissions.
2. Create a class.toml with roster & settings.

## Usage

gh-class assign <repo-name>
    creates private repos per student for a given template repository
"""

import os
import typer
from pathlib import Path
from typing import Annotated
from .client import GitHub, GitHubError
from .settings import load_config

app = typer.Typer(add_completion=False, help="GitHub Classroom replacement CLI")


def _quit(msg: str) -> None:
    typer.secho(f"error: {msg}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


@app.command()
def assign(
    template: Annotated[
        str, typer.Argument(help="Template repo: 'name' (in org) or 'owner/name'.")
    ],
    config: Annotated[
        Path, typer.Option("--config", "-c", help="Path to class.toml.")
    ] = Path("class.toml"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show plan, make no changes."),
    ] = False,
) -> None:
    """create student repositories"""

    ##### check environment ##############################
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        _quit("GITHUB_TOKEN is not set.")
    try:
        cfg = load_config(config)
    except Exception as e:
        _quit(f"could not load: {config}\n{e}")

    gh = GitHub(token, cfg.settings)

    # accept org_name/repo_name or just repo_name (defaulting to classroom org)
    t_owner, t_repo = template.split("/", 1) if "/" in template else (cfg.org, template)

    ##### validate github permissions ##############################
    typer.secho("validating...", fg=typer.colors.CYAN)
    if not gh.org_exists(cfg.org):
        _quit(f"org not accessible (check name and token scopes): {cfg.org}")

    # template repo available
    tmpl = gh.get_repo(t_owner, t_repo)
    if tmpl.status_code != 200:
        _quit(f"template not found: {t_owner}/{t_repo}")
    if not tmpl.json().get("is_template", False):
        _quit(
            f"not a template repo (enable 'Template repository' in settings): {t_owner}/{t_repo}"
        )

    # all usernames exist
    bad = [u for u in (*cfg.students, *cfg.staff) if not gh.user_exists(u)]
    if bad:
        _quit("unknown usernames: " + ", ".join(bad))

    planned = [(u, f"{t_repo}-{u}") for u in cfg.students]

    ##### create staff team if needed ###############################
    slug = cfg.settings.staff_team
    if not gh.team_exists(cfg.org, slug):
        if dry_run:
            typer.secho(
                f"would create staff team {cfg.org}/{slug}", fg=typer.colors.YELLOW
            )
        else:
            gh.create_team(cfg.org, slug)
            typer.echo(f"created team '{slug}'")
            for s in cfg.staff:
                # TODO: diff current team vs. TOML / dry-run
                gh.add_team_member(cfg.org, slug, s)

    typer.echo(f"staff team ready ({len(cfg.staff)} members)")

    ##### create student repos as needed #############################
    created = skipped = failed = 0
    for username, repo in planned:
        try:
            if gh.repo_exists(cfg.org, repo):
                skipped += 1
                tag = "skip"
            else:
                if dry_run:
                    typer.secho(
                        f"would create repo {cfg.org}/{repo}", fg=typer.color.YELLOW
                    )
                    continue
                else:
                    gh.generate_repo(t_owner, t_repo, cfg.org, repo)
                    # reconcile access on both new and existing repos
                    gh.add_collaborator(
                        cfg.org, repo, username, cfg.settings.student_permission
                    )
                    gh.grant_team_repo(
                        cfg.org, slug, repo, cfg.settings.staff_permission
                    )
                created += 1
                tag = "new "
            typer.echo(f"  [{tag}] {repo}")
        except GitHubError as e:
            failed += 1
            typer.secho(f"  [FAIL] {repo}: {e}", fg=typer.colors.RED)

    typer.secho(
        f"\ncreated {created} | skipped {skipped} | failed {failed}",
        fg=typer.colors.GREEN if not failed else typer.colors.YELLOW,
    )

    typer.secho(
        "note: student invites stay pending until each accepts",
        fg=typer.colors.CYAN,
    )
    if failed:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
