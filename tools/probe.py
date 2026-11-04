#!/usr/bin/env python3
"""Refresh the `cached` fields of a DecompDeck catalog.

For every project it queries GitHub Releases (once), picks the release matching
the project's channel, and records:
  - cached.latest_tag / cached.published_at  -> drives "update available"
  - cached.platforms                         -> lets the app pre-filter by OS
                                                without hitting GitHub per repo

This mirrors src-tauri/src/github.rs so the app and the CI agree. Run it in the
catalog repo's CI (see .github/workflows/probe.yml) and commit the result.

Usage:
    GITHUB_TOKEN=ghp_xxx python3 tools/probe.py src-tauri/catalog.seed.json
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import urllib.parse

API = "https://api.github.com"


def gh_get(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "decompdeck-probe",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def usable(r):
    """Non-draft AND with downloadable assets: a tag without builds (CI still
    running, notes-only release) must never become `latest_tag`, or the app
    offers an update that then fails with "no asset matches"."""
    return not r.get("draft") and bool(r.get("assets"))


def pick_release(releases, channel, rolling_tag):
    if channel == "rolling":
        for r in releases:
            if r.get("tag_name") == rolling_tag:
                return r
        return next((r for r in releases if usable(r)), None)
    if channel == "prerelease":
        return next((r for r in releases if usable(r)), None)
    stable = next((r for r in releases if usable(r) and not r.get("prerelease")), None)
    return stable or next((r for r in releases if usable(r)), None)


def pick_release_for(releases, channel, rolling_tag, rules):
    """The channel's pick among releases that carry a file some asset rule
    matches (a newest Android-only or notes-only release is skipped); the
    plain pick when none does. Same as the app's github::pick_release_for."""
    if channel == "rolling" and rolling_tag:
        return pick_release(releases, channel, rolling_tag)
    def matches(r):
        names = [a.get("name") or "" for a in r.get("assets", [])]
        return any(re.search(rx, n) for rx in rules for n in names)
    matching = [r for r in releases if matches(r)]
    return pick_release(matching, channel, rolling_tag) or pick_release(releases, channel, rolling_tag)


UPLOAD_RE = re.compile(r"\]\((/uploads/[0-9a-f]{16,64}/([^)\s]+))\)")


def gitlab_project_id(slug):
    pid = urllib.parse.quote(slug, safe="")
    req = urllib.request.Request(f"https://gitlab.com/api/v4/projects/{pid}", headers={"User-Agent": "decompdeck-probe"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("id")


def gitlab_releases(slug):
    """GitLab releases mapped to the GitHub shape probe/pick_release expect."""
    pid = urllib.parse.quote(slug, safe="")
    req = urllib.request.Request(f"https://gitlab.com/api/v4/projects/{pid}/releases?per_page=10",
                                 headers={"User-Agent": "decompdeck-probe"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.load(r)
    out = []
    project_id = None
    for v in raw:
        links = (v.get("assets") or {}).get("links") or []
        assets = [{"name": l.get("name"), "browser_download_url": l.get("direct_asset_url") or l.get("url")} for l in links]
        # Files uploaded into the notes only (Power Moon Recomp): as the app does.
        if not assets and "](/uploads/" in (v.get("description") or ""):
            if project_id is None:
                project_id = gitlab_project_id(slug)
            for m in UPLOAD_RE.finditer(v.get("description") or ""):
                name = urllib.parse.unquote(m.group(2))
                if all(a["name"] != name for a in assets):
                    assets.append({"name": name, "browser_download_url": f"https://gitlab.com/-/project/{project_id}{m.group(1)}"})
        out.append({
            "tag_name": v.get("tag_name"),
            "published_at": v.get("released_at"),
            "prerelease": bool(v.get("upcoming_release")),
            "draft": False,
            "assets": assets,
        })
    return out


def probe_project(p, token):
    repo = p["repo"]
    slug = f"{repo['owner']}/{repo['repo']}"
    try:
        if repo.get("host") == "gitlab":
            releases = gitlab_releases(slug)
        else:
            releases = gh_get(f"{API}/repos/{slug}/releases?per_page=10", token)
    except urllib.error.HTTPError as e:
        print(f"  ! {slug}: HTTP {e.code}")
        return None
    if not isinstance(releases, list):
        print(f"  ! {slug}: respuesta inesperada")
        return None
    if not releases:
        # The author removed every release (DMCA, takedown, rewrite…): forget
        # what we cached, or the app keeps offering an update that can't be
        # downloaded. Installed copies stay in the library untouched.
        print(f"  ! {slug}: sin releases (se vacía la caché)")
        return {"platforms": [], "latest_tag": None, "published_at": None}
    rel = pick_release_for(releases, p.get("release_channel", "stable"), p.get("rolling_tag"),
                           list(p.get("asset_rules", {}).values()))
    if not rel:
        print(f"  ! {slug}: sin release adecuada")
        return None

    names = [a["name"] for a in rel.get("assets", [])]
    platforms = [
        triple
        for triple, rx in p.get("asset_rules", {}).items()
        if any(re.search(rx, n) for n in names)
    ]
    cached = {
        "platforms": sorted(platforms),
        "latest_tag": rel.get("tag_name"),
        "published_at": rel.get("published_at"),
    }
    print(f"  ✓ {slug} @ {cached['latest_tag']}: {', '.join(platforms) or '—'}")
    return cached


def main():
    if len(sys.argv) < 2:
        print("uso: probe.py <catalog.json>")
        return 1
    path = sys.argv[1]
    token = os.environ.get("GITHUB_TOKEN")
    catalog = json.load(open(path))

    for p in catalog.get("projects", []):
        # Self-hosted (direct-download) projects have no GitHub releases to
        # probe; their cached fields are curated by hand.
        if p.get("direct") or p.get("repo", {}).get("host", "github") not in ("github", "gitlab"):
            continue
        cached = probe_project(p, token)
        if cached is not None:
            p["cached"] = cached
        time.sleep(0.3)  # be gentle with the API

    catalog["source"] = "probed"
    json.dump(catalog, open(path, "w"), indent=2, ensure_ascii=False)
    open(path, "a").write("\n")
    print(f"catálogo actualizado: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
