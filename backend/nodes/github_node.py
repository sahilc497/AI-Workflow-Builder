"""
GitHubNode – Unified GitHub node handling:
  GITHUB_PR        → list open pull requests
  GITHUB_API_CALL  → generic authenticated GitHub API call
  GITHUB_ACTION    → create_issue / list_issues / get_repo_status / create_repo
"""
import json
import os
import urllib.request
from .base import BaseNode


def _gh_request(url: str, method: str = "GET", payload: dict | None = None) -> dict | list:
    """Helper: make an authenticated GitHub API request and return parsed JSON."""
    token = os.getenv("GITHUB_TOKEN")
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "AI-Workflow-Builder")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"token {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _resolve_owner_repo(params: dict):
    owner = params.get("repo_owner")
    name = params.get("repo_name")
    if not owner or not name:
        repo_str = params.get("repo", "")
        if "/" in repo_str:
            owner, name = repo_str.split("/")[:2]
    return owner, name


# ── GITHUB_PR ──────────────────────────────────────────────────────────────

class GitHubPRNode(BaseNode):
    node_type = "GITHUB_PR"
    risk_level = "MEDIUM"

    def execute(self, params: dict, context: dict) -> str:
        owner, name = _resolve_owner_repo(params)
        if not owner or not name:
            return "GITHUB_PR: repo_owner and repo_name are required."
        data = _gh_request(f"https://api.github.com/repos/{owner}/{name}/pulls?state=open&per_page=5")
        if not data:
            return "No open pull requests found."
        return "Latest PRs:\n" + "\n".join(
            f"#{pr['number']} {pr['title']} (by {pr['user']['login']})" for pr in data
        )


# ── GITHUB_API_CALL ────────────────────────────────────────────────────────

class GitHubAPICallNode(BaseNode):
    node_type = "GITHUB_API_CALL"
    risk_level = "MEDIUM"

    def execute(self, params: dict, context: dict):
        endpoint = params.get("endpoint") or params.get("url", "")
        if not endpoint.startswith("http"):
            endpoint = "https://api.github.com" + ("/" if not endpoint.startswith("/") else "") + endpoint
        method = params.get("method", "GET").upper()
        try:
            return _gh_request(endpoint, method=method)
        except Exception as e:
            return f"GITHUB_API_CALL failed: {str(e)}"


# ── GITHUB_ACTION ──────────────────────────────────────────────────────────

class GitHubActionNode(BaseNode):
    node_type = "GITHUB_ACTION"
    risk_level = "MEDIUM"

    def execute(self, params: dict, context: dict) -> str:
        owner, name = _resolve_owner_repo(params)
        action_type = params.get("github_action_type", "")

        if action_type == "create_repo":
            repo_name = params.get("repo_name") or params.get("repo")
            if not repo_name:
                return "GITHUB_ACTION create_repo: repo_name is required."
            try:
                data = _gh_request("https://api.github.com/user/repos", method="POST", payload={
                    "name": repo_name, "private": True,
                    "description": params.get("description", "Created by AI-Workflow-Builder")
                })
                return f"Created repository '{data.get('full_name')}' at {data.get('html_url')}"
            except Exception as e:
                return f"create_repo failed: {str(e)}"

        if not owner or not name:
            return "GITHUB_ACTION: repo_owner and repo_name required (except for create_repo)."

        base = f"https://api.github.com/repos/{owner}/{name}"

        if action_type == "get_repo_status":
            try:
                d = _gh_request(base)
                return (f"Repo {owner}/{name}: ⭐ {d.get('stargazers_count', 0)} stars, "
                        f"{d.get('open_issues_count', 0)} open issues, "
                        f"last pushed {d.get('pushed_at', 'unknown')}")
            except Exception as e:
                return f"get_repo_status failed: {str(e)}"

        elif action_type == "list_issues":
            try:
                issues = _gh_request(f"{base}/issues?state=open&per_page=5")
                if not issues:
                    return "No open issues found."
                return "Open Issues:\n" + "\n".join(
                    f"#{i['number']} {i['title']}"
                    for i in issues if "pull_request" not in i
                )
            except Exception as e:
                return f"list_issues failed: {str(e)}"

        elif action_type == "create_issue":
            title = params.get("title") or "AI Workflow Alert"
            body = params.get("body", "")
            if not body and context:
                body = str(list(context.values())[-1])
            try:
                data = _gh_request(f"{base}/issues", method="POST",
                                   payload={"title": title, "body": body})
                return f"Created issue #{data.get('number')} at {data.get('html_url')}"
            except Exception as e:
                return f"create_issue failed: {str(e)}"

        return (f"GITHUB_ACTION: unsupported action_type '{action_type}'. "
                "Use: create_issue, list_issues, get_repo_status, create_repo.")
