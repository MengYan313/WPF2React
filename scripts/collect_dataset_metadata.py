"""缓存候选仓库的公开 GitHub 元数据与本地固定提交信息。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.parser.io_utils import read_json, write_json


USER_AGENT = "WPF2React-dataset-research"
COMMIT_COUNT_PATTERN = re.compile(r">([0-9][0-9,]*) Commits<")


def _request(url: str, *, token: str | None = None) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _git(project_path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(project_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _commit_count(repository: str, ref: str) -> int | None:
    encoded_ref = urllib.parse.quote(ref, safe="")
    url = f"https://github.com/{repository}/tree/{encoded_ref}"
    html = _request(url).decode("utf-8", errors="replace")
    match = COMMIT_COUNT_PATTERN.search(html)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))


def _license_paths(project_path: Path) -> list[str]:
    tree = _git(project_path, "ls-tree", "-r", "--name-only", "HEAD")
    return sorted(
        path
        for path in tree.splitlines()
        if Path(path).name.lower().startswith(("license", "copying"))
    )


def _api_metadata(repository: str, cache_path: Path, token: str | None) -> dict:
    if cache_path.is_file():
        return read_json(cache_path)

    data = json.loads(
        _request(f"https://api.github.com/repos/{repository}", token=token)
    )
    write_json(cache_path, data)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        default="results/dataset/candidate-seed.json",
        help="PDF 候选种子清单",
    )
    parser.add_argument(
        "--cache-dir",
        default="outputs/dataset-analysis/github-cache",
        help="GitHub REST 响应缓存目录",
    )
    parser.add_argument(
        "--output",
        default="outputs/dataset-analysis/github-metadata.json",
        help="规范化元数据输出文件",
    )
    args = parser.parse_args()

    seed = read_json(args.seed)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    records = []
    errors = []

    for candidate in seed["candidates"]:
        repository = candidate["repository"]
        local_dir = candidate["local_dir"]
        project_path = Path("repos") / local_dir
        cache_path = cache_dir / f"{repository.replace('/', '__')}.json"
        api_data = None
        api_error = None
        try:
            api_data = _api_metadata(repository, cache_path, token)
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            api_error = str(exc)
            errors.append({"repository": repository, "stage": "github_api", "error": api_error})

        commit_count = None
        commit_count_error = None
        try:
            commit_count = _commit_count(repository, candidate["analysis_ref"])
        except urllib.error.URLError as exc:
            commit_count_error = str(exc)
            errors.append(
                {"repository": repository, "stage": "commit_count", "error": commit_count_error}
            )
        if commit_count is None and not (project_path / ".git" / "shallow").exists():
            commit_count = int(_git(project_path, "rev-list", "--count", "HEAD"))

        github = {}
        if api_data:
            github = {
                "stars": api_data.get("stargazers_count"),
                "forks": api_data.get("forks_count"),
                "open_issues": api_data.get("open_issues_count"),
                "watchers": api_data.get("subscribers_count"),
                "created_at": api_data.get("created_at"),
                "updated_at": api_data.get("updated_at"),
                "pushed_at": api_data.get("pushed_at"),
                "archived": api_data.get("archived"),
                "disabled": api_data.get("disabled"),
                "fork": api_data.get("fork"),
                "default_branch": api_data.get("default_branch"),
                "primary_language": api_data.get("language"),
                "license_spdx": (api_data.get("license") or {}).get("spdx_id"),
                "size_kib": api_data.get("size"),
                "topics": api_data.get("topics", []),
            }

        records.append(
            {
                "repository": repository,
                "local_dir": local_dir,
                "analysis_ref": candidate["analysis_ref"],
                "commit_sha": _git(project_path, "rev-parse", "HEAD"),
                "commit_date": _git(project_path, "show", "-s", "--format=%cI", "HEAD"),
                "commit_count_at_ref": commit_count,
                "license_paths": _license_paths(project_path),
                "github": github,
                "api_error": api_error,
                "commit_count_error": commit_count_error,
            }
        )

    result = {
        "schema_version": 1,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "authenticated_api": bool(token),
        "records": records,
        "errors": errors,
    }
    write_json(args.output, result)
    print(
        f"GitHub 元数据: {args.output}，候选 {len(records)}，错误 {len(errors)}"
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
