#!/usr/bin/env python3
"""Assign/check `game_id` — the key that groups several projects of the SAME
game (e.g. Zelda64Recomp + 2Ship, both Majora's Mask) into one card in Freeport.

Default `game_id` = slug of `original_game` (accents stripped, lowercase,
non-alphanumerics → "-"). Two projects share a card when their `game_id`s match.
Override by hand in catalog.json when the default is wrong (same name, different
game) or too strict (a remaster/XBLA recomp you want grouped with the original).

Optional per-project `preferred: true` marks the version shown by default in a
group; without it the app prefers a native build for the platform, then the
most recent release.

    python3 tools/groups.py catalog.json          # fill missing game_id + report
    python3 tools/groups.py --check catalog.json  # exit 1 if any game_id missing
"""
import collections
import json
import re
import sys
import unicodedata


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", "and")
    s = re.sub(r"['’]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def with_game_id(p: dict, gid: str) -> dict:
    """Return a copy with `game_id` placed right after `original_game`."""
    out = {}
    for k, v in p.items():
        out[k] = v
        if k == "original_game":
            out["game_id"] = gid
    if "game_id" not in out:
        out["game_id"] = gid
    return out


def main() -> int:
    check = "--check" in sys.argv
    paths = [a for a in sys.argv[1:] if not a.startswith("--")] or ["catalog.json"]
    path = paths[0]
    cat = json.load(open(path, encoding="utf-8"))
    missing = [p["id"] for p in cat["projects"] if not p.get("game_id")]
    if check:
        if missing:
            print(f"✗ {len(missing)} proyectos sin game_id: {', '.join(missing)}")
            return 1
        print("✓ todos los proyectos tienen game_id")
    else:
        cat["projects"] = [
            p if p.get("game_id") else with_game_id(p, slug(p.get("original_game") or p["name"]))
            for p in cat["projects"]
        ]
        if missing:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cat, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"game_id asignado a {len(missing)} proyectos")
    groups = collections.defaultdict(list)
    for p in cat["projects"]:
        groups[p["game_id"]].append(p)
    multi = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"{len(groups)} juegos para {len(cat['projects'])} proyectos; {len(multi)} con varias versiones:")
    for k, v in multi.items():
        pref = [p["id"] for p in v if p.get("preferred")]
        print(f"  {k}: {', '.join(p['id'] for p in v)}" + (f"  (preferido: {pref[0]})" if pref else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
