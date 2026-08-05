#!/usr/bin/env python3
"""Fetch consistent boxart from ScreenScraper into the catalog.

For every project whose `system` maps to a ScreenScraper platform id, this
queries `jeuInfos` by game name, picks the `box-2D` media (region priority),
downloads it into `art/<id>.<ext>` (committed to this repo) and sets the
project's `box_art` field to the raw.githubusercontent URL. Clients then just
download the image from GitHub — they never need ScreenScraper credentials.

`cover_url` (libretro) is left untouched so the app's screenshot derivation
keeps working; the app prefers `box_art` for the cover when present.

ScreenScraper needs DEVELOPER credentials (granted to registered apps). A user
account raises the rate/thread limits. Set them via env:

    export SS_DEVID=... SS_DEVPASSWORD=...
    export SS_SSID=<user> SS_SSPASSWORD=<pass>   # optional but recommended
    python3 tools/art.py catalog.json

Then review + commit the new art/ files and catalog.json.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

API = "https://api.screenscraper.fr/api2"
SOFTNAME = "freeport"
RAW_BASE = "https://raw.githubusercontent.com/shadowlink/freeport-catalog/main/art"

# Our `system` id -> ScreenScraper platform id (systemeid). Best-effort; verify
# against https://api.screenscraper.fr/api2/systemesListe.php with your creds.
SS_SYS = {
    "n64": 14,      # Nintendo 64
    "psx": 57,      # PlayStation
    "genesis": 1,   # Megadrive / Genesis
    "segacd": 20,   # Mega-CD / Sega CD
    "gb": 9,        # Game Boy
    "gba": 12,      # Game Boy Advance
    "snes": 4,      # Super Nintendo
    "gc": 13,       # GameCube
    "wii": 16,      # Wii
    "amiga": 64,    # Commodore Amiga
    "x360": 33,     # Xbox 360
    "pc": 135,      # PC (DOS)
    "windows": 138, # PC (Windows)
}

REGION_PRIORITY = ["wor", "us", "eu", "jp", "ss", "fr"]


def creds():
    devid = os.environ.get("SS_DEVID")
    devpw = os.environ.get("SS_DEVPASSWORD")
    if not devid or not devpw:
        print("ERROR: faltan SS_DEVID / SS_DEVPASSWORD en el entorno.", file=sys.stderr)
        sys.exit(2)
    q = {
        "devid": devid,
        "devpassword": devpw,
        "softname": SOFTNAME,
        "output": "json",
    }
    if os.environ.get("SS_SSID"):
        q["ssid"] = os.environ["SS_SSID"]
        q["sspassword"] = os.environ.get("SS_SSPASSWORD", "")
    return q


def ss_get(endpoint, params):
    url = f"{API}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "freeport-art"})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # ScreenScraper returns plain-text on errors / quota problems.
        raise RuntimeError(raw.strip()[:200])


def pick_box2d(medias):
    boxes = [m for m in medias if m.get("type") == "box-2D"]
    if not boxes:
        return None
    for region in REGION_PRIORITY:
        for m in boxes:
            if m.get("region") == region:
                return m
    return boxes[0]


def download(url, dest, base_params):
    # The media URL from jeuInfos still needs the auth params appended.
    sep = "&" if "?" in url else "?"
    full = url + sep + urllib.parse.urlencode(base_params)
    req = urllib.request.Request(full, headers={"User-Agent": "freeport-art"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read()
    if len(data) < 512:
        raise RuntimeError(f"respuesta demasiado pequeña ({len(data)} bytes)")
    with open(dest, "wb") as f:
        f.write(data)
    return len(data)


def main():
    if len(sys.argv) < 2:
        print("uso: art.py <catalog.json>")
        return 1
    path = sys.argv[1]
    base = creds()
    catalog = json.load(open(path))
    art_dir = os.path.join(os.path.dirname(os.path.abspath(path)), "art")
    os.makedirs(art_dir, exist_ok=True)

    ok = miss = skip = 0
    for p in catalog.get("projects", []):
        sysid = SS_SYS.get(p.get("system"))
        if sysid is None:
            skip += 1
            continue
        name = p.get("original_game") or p.get("name") or ""
        if not name:
            skip += 1
            continue
        params = {**base, "systemeid": sysid, "romnom": name}
        try:
            data = ss_get("jeuInfos.php", params)
            medias = data.get("response", {}).get("jeu", {}).get("medias", [])
            box = pick_box2d(medias)
            if not box:
                print(f"  ? {p['id']}: sin box-2D para «{name}»")
                miss += 1
                time.sleep(1.0)
                continue
            fmt = box.get("format", "png").lower()
            fmt = "jpg" if fmt in ("jpeg", "jpg") else "png"
            fname = f"{p['id']}.{fmt}"
            n = download(box["url"], os.path.join(art_dir, fname), base)
            p["box_art"] = f"{RAW_BASE}/{fname}"
            print(f"  ✓ {p['id']}: box-2D {box.get('region')} ({n // 1024} KB)")
            ok += 1
        except (urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as e:
            print(f"  ! {p['id']}: {e}")
            miss += 1
        time.sleep(1.0)  # be gentle with the API / respect thread limits

    json.dump(catalog, open(path, "w"), indent=2, ensure_ascii=False)
    open(path, "a").write("\n")
    print(f"\nlisto: {ok} con box-2D, {miss} sin arte, {skip} sistemas no mapeados")
    print(f"arte en: {art_dir}  ·  revisa y commitea art/ + {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
