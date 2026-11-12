#!/usr/bin/env python3
"""Fill catalog entries with LaunchBox Games Database metadata (offline).

Reads the public Metadata.xml (https://gamesdb.launchbox-app.com/Metadata.zip,
unzipped) and writes, per project, an `lb` block:
    players, coop, rating, overview (English), and image URLs on
    images.launchbox-app.com: logo, snap, title, fanart.
Nothing is scraped at runtime: the app only reads these fields.

usage: python3 -I tools/launchbox.py <Metadata.xml> <catalog.json> [--dry]
"""
import json, re, sys, unicodedata
import xml.etree.ElementTree as ET

PLAT = {
    "n64": ["Nintendo 64"], "psx": ["Sony Playstation"], "ps2": ["Sony Playstation 2"],
    "ps3": ["Sony Playstation 3"], "ps4": ["Sony Playstation 4"], "psp": ["Sony PSP"],
    "gc": ["Nintendo GameCube"], "wii": ["Nintendo Wii"], "wiiu": ["Nintendo Wii U"],
    "nds": ["Nintendo DS"], "3ds": ["Nintendo 3DS"], "gb": ["Nintendo Game Boy", "Nintendo Game Boy Color"],
    "gba": ["Nintendo Game Boy Advance"], "dc": ["Sega Dreamcast"], "xbox": ["Microsoft Xbox"],
    "x360": ["Microsoft Xbox 360"], "switch": ["Nintendo Switch"], "switch2": ["Nintendo Switch 2", "Nintendo Switch"],
    "arcade": ["Arcade", "Sega Model 2", "Sega Model 3", "Namco System 22", "Sega Naomi"], "pc": ["Windows", "MS-DOS"],
}
REGION_PREF = ["North America", "World", None, "United States", "Europe", "United Kingdom", "Spain", "Japan"]
IMG = {"logo": "Clear Logo", "snap": "Screenshot - Gameplay", "title": "Screenshot - Game Title", "fanart": "Fanart - Background"}
BASE = "https://images.launchbox-app.com/"
# Catalog titles (often Spanish) that LaunchBox lists under another name.
ALIAS = {
    "Pokémon Rubí": "Pokémon Ruby Version", "Pokémon Zafiro": "Pokémon Sapphire Version",
    "Pokémon Negro": "Pokémon Black Version", "Pokémon Red / Blue": "Pokémon Red Version",
    "Pokémon Sword and Shield": "Pokémon Sword", "Breath of Fire III": "Breath of Fire III",
    "Pokémon: Let's Go, Pikachu! and Let's Go, Eevee!": "Pokémon: Let's Go, Pikachu!",
    "James Bond 007: Nightfire": "007: NightFire", "Burnout 2: Point of Impact": "Burnout 2: Point of Impact Developer's Cut",
    "Civilization Revolution": "Sid Meier's Civilization Revolution",
    "Resident Evil Code: Veronica X": "Resident Evil Code: Veronica X HD",
    "Tekken Tag Tournament 2": "Tekken Tag Tournament 2: Wii U Edition",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s).replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(the|a)\b", " ", s)
    return " ".join(s.split())


def main():
    xml, cat_path = sys.argv[1], sys.argv[2]
    dry = "--dry" in sys.argv
    cat = json.load(open(cat_path, encoding="utf-8"))
    want_plats = {p for v in PLAT.values() for p in v}

    games, names, imgs = {}, {}, {}
    for _, el in ET.iterparse(xml, events=("end",)):
        tag = el.tag
        if tag == "Game":
            plat = el.findtext("Platform") or ""
            if plat in want_plats:
                gid = el.findtext("DatabaseID")
                games[gid] = {
                    "name": el.findtext("Name") or "", "plat": plat,
                    "players": el.findtext("MaxPlayers"), "coop": el.findtext("Cooperative") == "true",
                    "rating": el.findtext("CommunityRating"), "votes": el.findtext("CommunityRatingCount"),
                    "overview": (el.findtext("Overview") or "").strip(),
                }
                names.setdefault((plat, norm(games[gid]["name"])), gid)
            el.clear()
        elif tag == "GameAlternateName":
            gid = el.findtext("DatabaseID")
            if gid in games:
                names.setdefault((games[gid]["plat"], norm(el.findtext("AlternateName") or "")), gid)
            el.clear()
        elif tag == "GameImage":
            gid = el.findtext("DatabaseID")
            if gid in games:
                t = el.findtext("Type")
                for k, v in IMG.items():
                    if t == v:
                        reg = el.findtext("Region")
                        rank = REGION_PREF.index(reg) if reg in REGION_PREF else 99
                        cur = imgs.setdefault(gid, {}).get(k)
                        if cur is None or rank < cur[0]:
                            imgs[gid][k] = (rank, el.findtext("FileName"))
            el.clear()

    hit = miss = 0
    missed = []
    for p in cat["projects"]:
        plats = PLAT.get(p["system"], [])
        cands = [ALIAS.get(p.get("original_game") or "", ""), p.get("original_game") or "", p.get("wiki") or "", p.get("name") or ""]
        gid = None
        for c in cands:
            n = norm(c)
            if not n:
                continue
            for pl in plats:
                gid = names.get((pl, n))
                if gid:
                    break
            if gid:
                break
            # «Title: Subtitle» vs «Title»
            base = norm(re.split(r"[:–-]", c)[0])
            for pl in plats:
                if len(base) > 5:
                    gid = names.get((pl, base))
                    if gid:
                        break
            if gid:
                break
        if not gid:
            miss += 1
            missed.append(f'{p["system"]}: {p.get("original_game")}')
            p.pop("lb", None)
            continue
        hit += 1
        g = games[gid]
        if "--show" in sys.argv and norm(g["name"]) != norm(p.get("original_game") or ""):
            print(f'  ~ {p["system"]}: {p.get("original_game")}  ->  {g["name"]}')
        lb = {"id": int(gid)}
        if g["players"] and g["players"].isdigit() and int(g["players"]) > 0:
            lb["players"] = int(g["players"])
        if g["coop"]:
            lb["coop"] = True
        try:
            if g["rating"] and int(g["votes"] or 0) >= 3:
                lb["rating"] = round(float(g["rating"]), 1)
        except ValueError:
            pass
        if g["overview"]:
            lb["overview"] = g["overview"][:1200]
        for k in IMG:
            if k in imgs.get(gid, {}):
                lb[k] = BASE + imgs[gid][k][1]
        p["lb"] = lb

    print(f"con datos: {hit}  sin coincidencia: {miss}")
    for m in missed:
        print("  -", m)
    if not dry:
        with open(cat_path, "w", encoding="utf-8") as f:
            json.dump(cat, f, indent=2, ensure_ascii=False)
            f.write("\n")


if __name__ == "__main__":
    main()
