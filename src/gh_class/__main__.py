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


class Theme:
    ERROR = typer.colors.RED
    OK = typer.colors.CYAN
    DRY = typer.colors.MAGENTA
    ADD = typer.colors.GREEN
    WARN = typer.colors.YELLOW


def _quit(msg: str) -> None:
    typer.secho(f"error: {msg}", fg=Theme.ERROR, err=True)
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

    gh = GitHub(token, cfg)

    # validate org exists & is accessible via API
    if not gh.org_exists(cfg.org):
        _quit(f"org not accessible (check name and token scopes): {cfg.org}")

    return cfg, gh


def _sync_team(gh, org, team, cfg_members, dry_run):
    members = set()
    invites = set()
    current_set = set(cfg_members)

    # create team if needed
    if not gh.team_exists(org, team):
        if dry_run:
            typer.secho(f"would create team {org} - {team}", fg=Theme.DRY)
        else:
            gh.create_team(org, team)
            typer.echo(f"created team '{team}'")
    else:
        members = set(gh.get_team_members(org, team))
        invites = set(gh.get_team_invites(org, team))

    # already all set!
    if current_set == members:
        typer.secho(
            f"team '{team}' already initialized, {len(members)} members", fg=Theme.OK
        )

    # add people that do not have membership or a pending invite
    to_add = current_set - (members | invites)
    for m in to_add:
        if dry_run:
            typer.secho(f"would add {m} to {team}", fg=Theme.DRY)
        else:
            typer.secho(f"{m} invited to {team}", fg=Theme.ADD)
            gh.add_team_member(org, team, m)

    # remove anyone with permissions that doesn't appear in config
    to_remove = members - current_set
    for m in to_remove:
        if dry_run:
            typer.secho(f"would remove {m} from {team}", fg=Theme.DRY)
        else:
            gh.remove_team_member(org, team, m)
            typer.secho(f"{m} removed from {team}", fg=Theme.WARN)

    # show status of invites.
    # does not remove invites of students that should be purged as
    #  this is a rare edge case and adds a complexity w/ GH data model
    # mistakenly added students can be removed via browser if urgent
    to_uninvite = invites - (current_set | members)
    for m in invites:
        if m in to_uninvite:
            typer.secho(
                f"{m} has been removed but has an invite to {team} (remove or let expire)",
                fg=Theme.ERROR,
            )
        else:
            typer.secho(f"{m} has a pending invite to {team}", fg=Theme.OK)


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
    if not dry_run:
        typer.secho("locking down default org settings\n  (hidden repos by default/no student creation)", fg=Theme.OK)
        gh.patch_org(
            cfg.org,
            {
                "default_repository_permission": "none",
                "members_can_create_repositories": False,
            },
        )
    _sync_team(gh, cfg.org, cfg.staff_team, cfg.staff, dry_run)
    _sync_team(gh, cfg.org, cfg.student_team, cfg.students, dry_run)


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
                    typer.secho(f"would create repo {cfg.org}/{repo}", fg=Theme.DRY)
                    continue
                else:
                    gh.generate_repo(t_owner, t_repo, cfg.org, repo)
                    # reconcile access on both new and existing repos
                    gh.add_collaborator(cfg.org, repo, username, cfg.student_permission)
                    gh.grant_team_repo(
                        cfg.org, cfg.staff_team, repo, cfg.staff_permission
                    )
                created += 1
                tag = "new "
            typer.secho(
                f"  [{tag}] {repo}", fg=Theme.ADD if tag == "new " else Theme.OK
            )
        except GitHubError as e:
            failed += 1
            typer.secho(f"  [FAIL] {repo}: {e}", fg=Theme.ERROR)

    typer.secho(
        f"\ncreated {created} | skipped {skipped} | failed {failed}",
        fg=Theme.OK if not failed else Theme.ERROR,
    )
    if failed:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
