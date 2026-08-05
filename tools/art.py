#!/usr/bin/env python3
"""Fill each project's `box_art` with a uniform vertical capsule from SteamGridDB.

SteamGridDB "grids" are 2:3 vertical library capsules (600x900), the same shape
for every game — ideal for a tidy grid with no cropping. This searches each game
by name, picks the top vertical grid, and stores its public CDN URL in `box_art`.
No images are re-hosted (the CDN URL is public); the app downloads + thumbnails
it like any cover, and `cover_url` (libretro) still drives the screenshots.

Get a free API key at https://www.steamgriddb.com/profile/preferences/api

    export SGDB_KEY=...
    python3 tools/art.py catalog.json

Then review + commit catalog.json.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

API = "https://www.steamgriddb.com/api/v2"
# Vertical capsule sizes (valid SteamGridDB dimensions only). Any grid as fallback.
VERTICAL = "600x900,342x482,660x930"


def sgdb_get(path, key):
    req = urllib.request.Request(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {key}", "User-Agent": "freeport-art"},
    )
    with urllib.request.urlopen(req, timeout=40) as r:
        data = json.load(r)
    if not data.get("success"):
        raise RuntimeError(str(data.get("errors") or data))
    return data.get("data")


def find_game_id(name, key):
    term = urllib.parse.quote(name, safe="")  # encode '/' too
    results = sgdb_get(f"/search/autocomplete/{term}", key)
    if not results:
        return None
    return results[0]["id"]  # best match first


def best_grid_url(game_id, key):
    q = f"?dimensions={VERTICAL}&types=static&nsfw=false&humor=false"
    grids = sgdb_get(f"/grids/game/{game_id}{q}", key)
    if not grids:
        # fall back to any grid if no vertical one exists
        grids = sgdb_get(f"/grids/game/{game_id}?types=static&nsfw=false", key)
    if not grids:
        return None
    # SteamGridDB returns most-relevant first; prefer higher upvotes if present.
    grids.sort(key=lambda g: g.get("upvotes", 0), reverse=True)
    return grids[0].get("url")


def main():
    if len(sys.argv) < 2:
        print("uso: art.py <catalog.json>")
        return 1
    key = os.environ.get("SGDB_KEY")
    if not key:
        print("ERROR: falta SGDB_KEY en el entorno.", file=sys.stderr)
        return 2
    path = sys.argv[1]
    catalog = json.load(open(path))

    ok = miss = 0
    for p in catalog.get("projects", []):
        name = p.get("original_game") or p.get("name") or ""
        if not name:
            miss += 1
            continue
        try:
            gid = find_game_id(name, key)
            if gid is None:
                print(f"  ? {p['id']}: sin resultado para «{name}»")
                miss += 1
                time.sleep(0.3)
                continue
            url = best_grid_url(gid, key)
            if not url:
                print(f"  ? {p['id']}: «{name}» sin grid vertical")
                miss += 1
            else:
                p["box_art"] = url
                print(f"  ✓ {p['id']}: {url.rsplit('/', 1)[-1]}")
                ok += 1
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as e:
            print(f"  ! {p['id']}: {e}")
            miss += 1
        time.sleep(0.3)  # gentle

    json.dump(catalog, open(path, "w"), indent=2, ensure_ascii=False)
    open(path, "a").write("\n")
    print(f"\nlisto: {ok} con box_art, {miss} sin arte  ·  revisa y commitea {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
