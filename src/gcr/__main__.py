"""
gh-class: minimal GitHub classroom replacement CLI
"""

import os
import typer
import subprocess
import shutil
import enum
from rich.table import Table
from rich.console import Console
from rich.prompt import Prompt, Confirm
from pathlib import Path
from typing import Annotated
from importlib.metadata import version as get_version
from .client import GitHub, GitHubError
from .settings import load_config, Config

app = typer.Typer(add_completion=False, help="GitHub Classroom replacement CLI")


def version_callback(value: bool) -> None:
    if value:
        v = get_version("gcr-cli")
        print(f"gcr {v}")
        raise typer.Exit()


@app.callback()
def common(
    ctx: typer.Context,
    version: bool = typer.Option(None, "--version", callback=version_callback),
) -> None:
    pass


class Action(enum.Enum):
    NONE = "—"
    ADD = "add"
    REMOVE = "remove"
    ORPHAN = "remove invite (manual)"  # can't auto-delete without invite ID


_STYLE = {
    Action.ADD: "green",
    Action.REMOVE: "red",
    Action.ORPHAN: "yellow",
    Action.NONE: "dim",
}


class Theme:
    ERROR = typer.colors.RED
    OK = typer.colors.CYAN
    DRY = typer.colors.MAGENTA
    ADD = typer.colors.GREEN
    WARN = typer.colors.YELLOW


def _quit(msg: str) -> None:
    typer.secho(f"error: {msg}", fg=Theme.ERROR, err=True)
    raise typer.Exit(1)


def _check_env(config_path: Path) -> tuple[Config, GitHub]:
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


def _plan_team(
    gh: GitHub, org: str, team: str, cfg_members: list[str]
) -> list[tuple[str, str, Action]]:
    desired = set(cfg_members)
    members = set()
    invites = set()
    if gh.team_exists(org, team):
        members = set(gh.get_team_members(org, team))
        invites = set(gh.get_team_invites(org, team))
    plan = []
    for u in sorted(desired | members | invites):
        in_cfg = u in desired
        if u in members:
            action = Action.NONE if in_cfg else Action.REMOVE
            status = "member"
        elif u in invites:
            action = Action.NONE if in_cfg else Action.ORPHAN
            status = "invited"
        else:  # in roster only
            action, status = Action.ADD, "-"
        plan.append((u, status, action))

    return plan


def _sync_team(
    gh: GitHub, org: str, team: str, cfg_members: list[str], dry_run: bool
) -> None:
    plan = _plan_team(gh, org, team, cfg_members)

    table = Table(title=team, header_style="bold")
    for col in ("username", "current status", "action"):
        table.add_column(col)
    for user, status, action in plan:
        table.add_row(user, status, action.value, style=_STYLE[action])
    Console().print(table)

    changes = sum(1 for _, _, a in plan if a in (Action.ADD, Action.REMOVE))

    if (
        dry_run
        or changes == 0
        or not Confirm.ask(f"proceed to make {changes} changes?")
    ):
        return

    # not a dry run, can make changes now
    if not gh.team_exists(org, team):
        gh.create_team(org, team)

    for user, _, action in plan:
        if action is Action.ADD:
            try:
                gh.add_team_member(org, team, user)
            except GitHubError as e:
                typer.secho(f"error adding {user}: {e}", fg=Theme.ERROR)
        elif action is Action.REMOVE:
            gh.remove_team_member(org, team, user)

    # ORPHAN is currently unresolved
    #  this is a rare edge case and adds a complexity w/ GH data model
    #  mistakenly invited students can be removed via browser if urgent


@app.command()
def setup(
    config: Annotated[
        Path, typer.Option("--config", "-c", help="Path to class.toml.")
    ] = Path("class.toml"),
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show plan, make no changes."),
    ] = False,
) -> None:
    """initialize classroom org"""
    cfg, gh = _check_env(config)
    if not dry_run:
        typer.secho(
            "locking down default org settings\n"
            "  (hidden repos by default/no student creation)",
            fg=Theme.OK,
        )
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
    empty: Annotated[
        bool,
        typer.Option(
            "--empty", help="Don't use template, generate empty repo w/ name."
        ),
    ] = False,
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

    if not empty:
        # template repo available
        tmpl = gh.get_repo(t_owner, t_repo)
        if tmpl.status_code != 200:
            _quit(f"template not found: {t_owner}/{t_repo}")
        if not tmpl.json().get("is_template", False):
            if (
                Confirm.ask(
                    f"{t_owner}/{t_repo} is not a template repository, convert?"
                )
                and not dry_run
            ):
                gh.patch_repo(t_owner, t_repo, {"is_template": True})
            else:
                _quit("not a template repo")

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
                    if empty:
                        gh.generate_empty_repo(cfg.org, repo)
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


@app.command()
def clone(
    assignment: Annotated[str, typer.Argument(help="Assignment slug.")],
    student: Annotated[str, typer.Argument(help="Student name.")] = "all",
    config: Annotated[
        Path, typer.Option("--config", "-c", help="Path to class.toml.")
    ] = Path("class.toml"),
) -> None:
    """clone student repositories"""

    cfg, gh = _check_env(config)

    def _clone(user: str) -> None:
        repo = f"{assignment}-{user}"
        tmpl = gh.get_repo(cfg.org, repo)
        if tmpl.status_code != 200:
            _quit(f"repo not found: {cfg.org}/{repo}")

        clone_url = f"git@github.com:{cfg.org}/{repo}"
        dest = Path(cfg.checkout_path) / repo
        if dest.exists():
            resp = Prompt.ask(
                f"{dest} already exists, (S)kip/(r)eplace/(a)bort?",
                choices=["s", "r", "a"],
                default="s",
            )
            if resp == "s":
                return
            elif resp == "r":
                shutil.rmtree(dest)
                typer.secho(f"removed {dest}", fg=Theme.WARN)
            elif resp == "a":
                raise typer.Exit(1)
        subprocess.run(
            ["git", "clone", clone_url, dest],
            check=True,
            capture_output=True,
            text=True,
        )
        typer.secho(f"cloned {dest}", fg=Theme.ADD)

    if student == "all":
        for repo in gh.get_repos(cfg.org, assignment + "-"):
            sslug = repo.replace(assignment + "-", "")
            _clone(sslug)
    else:
        _clone(student)


if __name__ == "__main__":
    app()
