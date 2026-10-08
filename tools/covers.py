#!/usr/bin/env python3
"""Carátulas homogéneas: la caja original de cada sistema, de los thumbnails de
libretro (escaneos No-Intro/Redump), y SteamGridDB solo donde libretro no llega
(Xbox 360, PS5, juegos de PC fuera de DOS).

Para cada proyecto busca `original_game` en el índice `Named_Boxarts` de la
carpeta libretro de su sistema, prefiriendo USA > World > USA, Europe > Europe >
Japan y evitando Demo/Beta/Proto/Rev si hay alternativa. Si no hay caja, pide a
SteamGridDB la "grid" vertical 600x900 más votada. Deja `cover_url` y vacía
`box_art` (la app prefiere `box_art`, y aquí la caja original manda).

    python3 tools/covers.py catalog.json            # solo los que no son libretro
    python3 tools/covers.py --all catalog.json      # rehace todos
    python3 tools/covers.py --report catalog.json   # no escribe
Clave SGDB: SGDB_KEY o ~/.config/freeport-catalog/sgdb_key.
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

LR = "https://thumbnails.libretro.com/"
FOLDERS = {
    "n64": ["Nintendo - Nintendo 64"], "psx": ["Sony - PlayStation"],
    "gb": ["Nintendo - Game Boy Color", "Nintendo - Game Boy"], "gba": ["Nintendo - Game Boy Advance"],
    "gc": ["Nintendo - GameCube"], "wii": ["Nintendo - Wii"], "nds": ["Nintendo - Nintendo DS"],
    "ps2": ["Sony - PlayStation 2"], "psp": ["Sony - PlayStation Portable"], "3ds": ["Nintendo - Nintendo 3DS"],
    "dc": ["Sega - Dreamcast"], "xbox": ["Microsoft - Xbox"], "pc": ["DOS"], "arcade": ["MAME"], "wiiu": ["Nintendo - Wii U"],
    # x360 y ps5: libretro casi no tiene cajas (12 y 20 entradas) → SteamGridDB
    # para todo el sistema, así al menos son homogéneas entre sí.
}
REGION_RANK = ["(usa)", "(world)", "(usa, europe)", "(usa, canada)", "(europe)", "(japan, usa)", "(japan)", "(australia)"]
BAD = re.compile(r"\((demo|beta|proto|sample|kiosk|rev \d|v\d|virtual console|aftermarket|unl|pirate)", re.I)
CACHE = os.path.expanduser("~/.cache/freeport-catalog/libretro")


def fetch(url, headers=None, raw=True):
    req = urllib.request.Request(url, headers={"User-Agent": "freeport-covers", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
        return data.decode("utf-8", "replace") if raw else json.loads(data)


def index(folder):
    os.makedirs(CACHE, exist_ok=True)
    f = os.path.join(CACHE, folder.replace(" ", "_") + ".json")
    if os.path.exists(f) and time.time() - os.path.getmtime(f) < 7 * 86400:
        return json.load(open(f))
    html = fetch(LR + urllib.parse.quote(folder) + "/Named_Boxarts/")
    names = [urllib.parse.unquote(m[6:-5]) for m in re.findall(r'href="[^"]*\.png"', html)]
    json.dump(names, open(f, "w"))
    return names


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"^the\s+", "", s)
    s = s.replace("&", "and").replace("pokemon", "pokemon")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def base_name(entry):
    # "Legend of Zelda, The - Majora's Mask (USA)" -> "the legend of zelda majoras mask"
    name = re.sub(r"\s*\(.*$", "", entry)
    name = re.sub(r"^(.*?), The( - |$)", r"The \1\2", name)
    return norm(name)


def pick(cands):
    def key(e):
        low = e.lower()
        bad = 1 if BAD.search(low) else 0
        rank = next((i for i, r in enumerate(REGION_RANK) if r in low), len(REGION_RANK))
        return (bad, rank, len(e))
    return sorted(cands, key=key)[0]


def libretro_cover(system, title):
    want = norm(title)
    for folder in FOLDERS.get(system, []):
        names = index(folder)
        exact = [n for n in names if base_name(n) == want]
        if not exact:
            # tolerate subtitle punctuation differences: "R4 - Ridge Racer Type 4" vs "R4: Ridge Racer Type 4"
            exact = [n for n in names if base_name(n).replace(" ", "") == want.replace(" ", "")]
        if exact:
            chosen = pick(exact)
            return LR + urllib.parse.quote(folder) + "/Named_Boxarts/" + urllib.parse.quote(chosen) + ".png", folder
    return None, None


def sgdb_cover(title, key):
    h = {"Authorization": f"Bearer {key}"}
    res = fetch(f"https://www.steamgriddb.com/api/v2/search/autocomplete/{urllib.parse.quote(title, safe='')}", h, raw=False)
    if not res.get("success") or not res["data"]:
        return None
    gid = res["data"][0]["id"]
    grids = fetch(f"https://www.steamgriddb.com/api/v2/grids/game/{gid}?dimensions=600x900&types=static&nsfw=false&humor=false", h, raw=False)
    data = grids.get("data") or []
    if not data:
        grids = fetch(f"https://www.steamgriddb.com/api/v2/grids/game/{gid}?types=static&nsfw=false", h, raw=False)
        data = grids.get("data") or []
    if not data:
        return None
    # Prefer the plain "alternate" style (usually the real box art), then votes.
    data.sort(key=lambda g: (0 if g.get("style") == "alternate" else 1, -g.get("upvotes", 0)))
    return data[0]["url"]


def main():
    redo_all = "--all" in sys.argv
    report = "--report" in sys.argv
    path = ([a for a in sys.argv[1:] if not a.startswith("--")] or ["catalog.json"])[0]
    key = os.environ.get("SGDB_KEY")
    if not key:
        try:
            key = open(os.path.expanduser("~/.config/freeport-catalog/sgdb_key")).read().strip()
        except OSError:
            key = None
    cat = json.load(open(path, encoding="utf-8"))
    stats = {"libretro": 0, "sgdb": 0, "kept": 0, "miss": 0}
    for p in cat["projects"]:
        cur = p.get("cover_url") or ""
        if not redo_all and "libretro" in cur:
            p["box_art"] = None
            stats["kept"] += 1
            continue
        title = p.get("original_game") or p["name"]
        # `cover_name`: nombre exacto del fichero libretro (sin .png) cuando el
        # título no casa (p. ej. juegos japoneses con nombre romanizado).
        url, folder = None, None
        if p.get("cover_name"):
            for folder in FOLDERS.get(p["system"], []):
                if p["cover_name"] in index(folder):
                    url = LR + urllib.parse.quote(folder) + "/Named_Boxarts/" + urllib.parse.quote(p["cover_name"]) + ".png"
                    break
        if not url:
            url, folder = libretro_cover(p["system"], title)
        src = "libretro"
        if not url and key and p["system"] in ("x360", "ps5", "pc"):
            try:
                url = sgdb_cover(title, key)
                src = "sgdb"
                time.sleep(0.3)
            except Exception as e:
                print(f"  ! sgdb {p['id']}: {e}")
        if url:
            p["cover_url"] = url
            p["box_art"] = None
            stats[src] += 1
            print(f"  ✓ {src:8} {p['id']:34} {urllib.parse.unquote(url.rsplit('/', 1)[-1])[:70]}")
        else:
            stats["miss"] += 1
            print(f"  ? sin caja  {p['id']:34} «{title}» ({p['system']}) — se conserva: {cur[:60] or 'nada'}")
    print(f"\nlibretro {stats['libretro']} · sgdb {stats['sgdb']} · ya libretro {stats['kept']} · sin resolver {stats['miss']}")
    if not report:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cat, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
