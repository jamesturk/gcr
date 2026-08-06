"""
gh-class: minimal GitHub classroom replacement CLI
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


def _check_env(config_path: Path):
    """check that token & config are present & return them"""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        _quit("GITHUB_TOKEN is not set.")
    try:
        cfg = load_config(config_path)
    except Exception as e:
        _quit(f"could not load: {config_path}\n{e}")

    gh = GitHub(token, cfg.settings)

    # validate org exists & is accessible via API
    if not gh.org_exists(cfg.org):
        _quit(f"org not accessible (check name and token scopes): {cfg.org}")

    return cfg, gh


@app.command()
def setup(
    config: Annotated[
        Path, typer.Option("--config", "-c", help="Path to class.toml.")
    ] = Path("class.toml"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show plan, make no changes."),
    ] = False,
):
    """initialize classroom org"""

    cfg, gh = _check_env(config)

    team = cfg.settings.staff_team
    members = set()
    if not gh.team_exists(cfg.org, team):
        if dry_run:
            typer.secho(
                f"would create staff team {cfg.org}/{team}", fg=typer.colors.YELLOW
            )
        else:
            gh.create_team(cfg.org, team)
            typer.echo(f"created team '{team}'")
    else:
        members = set(gh.get_team_members(cfg.org, team))

    # member diff
    staff_set = set(cfg.staff)

    if staff_set == members:
        typer.secho(f"staff team already initialized, {len(members)} members", fg=typer.colors.GREEN)
        return # done!

    to_add = staff_set - members
    to_remove = members - staff_set

    for m in to_add:
        if dry_run:
            typer.secho(f"would add {m} to {team}", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"adding {m} to {team}", fg=typer.colors.YELLOW)
            gh.add_team_member(cfg.org, team, m)

    for m in to_remove:
        if dry_run:
            typer.secho(f"would remove {m} from {team}", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"removing {m} from {team}", fg=typer.colors.YELLOW)
            gh.remove_team_member(cfg.org, team, m)


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

    cfg, gh = _check_env(config)

    # accept org_name/repo_name or just repo_name (defaulting to classroom org)
    t_owner, t_repo = template.split("/", 1) if "/" in template else (cfg.org, template)

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

    # create student repos as needed
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
        "note: students must still accept repository invites",
        fg=typer.colors.CYAN,
    )
    if failed:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
