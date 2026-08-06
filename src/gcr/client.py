import httpx2
from careful.httpx import make_careful_client
from .settings import Config

API = "https://api.github.com"
API_VERSION = "2022-11-28"


class GitHubError(Exception):
    pass


def _check(resp: httpx2.Response, ok: tuple[int, ...], what: str) -> None:
    if resp.status_code not in ok:
        try:
            detail = resp.json().get("message", "")
        except Exception:
            detail = ""
        raise GitHubError(f"HTTP {resp.status_code} {detail}".strip() + f" ({what})")


def _should_retry(resp: httpx2.Response) -> bool:
    # retry intermittent failures
    return resp.status_code >= 500 or resp.status_code == 429


class GitHub:
    def __init__(self, token: str, settings: Config) -> None:
        base = httpx2.Client(
            base_url=API,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
            },
            timeout=30.0,
        )
        self.c = make_careful_client(
            client=base,
            retry_attempts=settings.retry_attempts,
            retry_wait_seconds=settings.retry_wait_seconds,
            should_retry=_should_retry,
            requests_per_minute=settings.requests_per_minute,
        )

    def user_exists(self, username: str) -> bool:
        return self.c.get(f"/users/{username}").status_code == 200

    def org_exists(self, org: str) -> bool:
        return self.c.get(f"/orgs/{org}").status_code == 200

    def get_repo(self, org: str, repo: str) -> httpx2.Response:
        return self.c.get(f"/repos/{org}/{repo}")

    def repo_exists(self, org: str, repo: str) -> bool:
        return self.c.get(f"/repos/{org}/{repo}").status_code == 200

    def team_exists(self, org: str, slug: str) -> bool:
        return self.c.get(f"/orgs/{org}/teams/{slug}").status_code == 200

    def get_team_invites(self, org: str, slug: str) -> bool:
        # TODO: paginate for >100
        r = self.c.get(
            f"/orgs/{org}/teams/{slug}/invitations", params={"per_page": 100}
        )
        _check(r, (200,), f"get invites of {org}/{slug}")
        members = [m["login"] for m in r.json()]
        return members

    def get_team_members(self, org: str, slug: str) -> bool:
        # TODO: paginate for >100
        r = self.c.get(f"/orgs/{org}/teams/{slug}/members", params={"per_page": 100})
        _check(r, (200,), f"get members of {org}/{slug}")
        members = [m["login"] for m in r.json()]
        return members

    def patch_org(self, org: str, payload: dict) -> None:
        r = self.c.patch(f"/orgs/{org}", json=payload)
        _check(r, (200,), f"patch org settings {org} {payload}")
        for key, val in payload.items():
            assert r.json()[key] == val

    def create_team(self, org: str, name: str) -> None:
        r = self.c.post(f"/orgs/{org}/teams", json={"name": name, "privacy": "closed"})
        _check(r, (201,), f"create team {name}")

    def add_team_member(self, org: str, slug: str, username: str) -> None:
        r = self.c.put(
            f"/orgs/{org}/teams/{slug}/memberships/{username}",
            json={"role": "member"},
        )
        _check(r, (200,), f"add {username} to team {slug}")

    def remove_team_member(self, org: str, slug: str, username: str) -> None:
        r = self.c.delete(
            f"/orgs/{org}/teams/{slug}/memberships/{username}",
        )
        _check(r, (204,), f"remove {username} from team {slug}")

    # def remove_team_invite(self, org: str, slug: str, username: str) -> None:
    # # TODO: if needed, need to fetch invite ID first
    #     r = self.c.delete(
    #         f"/orgs/{org}/teams/{slug}/invitations/{username}",
    #     )
    #     _check(r, (204,), f"remove {username} invite from team {slug}")

    def generate_repo(self, t_owner: str, t_repo: str, org: str, name: str) -> None:
        r = self.c.post(
            f"/repos/{t_owner}/{t_repo}/generate",
            json={"owner": org, "name": name, "private": True},
        )
        _check(r, (201,), f"create repo {name}")

    def add_collaborator(self, org: str, repo: str, username: str, perm: str) -> None:
        r = self.c.put(
            f"/repos/{org}/{repo}/collaborators/{username}",
            json={"permission": perm},
        )
        # 201 = invitation created, 204 = already had access
        _check(r, (201, 204), f"add collaborator {username} to {repo}")

    def grant_team_repo(self, org: str, slug: str, repo: str, perm: str) -> None:
        r = self.c.put(
            f"/orgs/{org}/teams/{slug}/repos/{org}/{repo}",
            json={"permission": perm},
        )
        _check(r, (204,), f"grant team {slug} on {repo}")
