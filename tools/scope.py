#!/usr/bin/env python3
"""Regla de alcance del catálogo (decisión 2026-10-01).

Freeport cubre consolas desde la generación PS1/N64 en adelante, más juegos de PC.
Por debajo (NES, SNES, Mega Drive, Sega CD, Game Boy/Color) y los ordenadores de
la época (Amiga) la emulación es perfecta y una recompilación nativa no aporta nada.

Excepción: un port de una máquina vetada puede entrar si es realmente bueno,
querido por la comunidad y trabajado hasta el extremo. Se declara con el campo
`exception` (texto que explica el porqué). Sin ese campo, la CI rechaza la entrada.

    python3 tools/scope.py --check catalog.json
"""
import json
import sys

VETOED = {"nes", "snes", "genesis", "segacd", "gb", "amiga", "sms", "gg", "fds"}


def main() -> int:
    path = [a for a in sys.argv[1:] if not a.startswith("--")] or ["catalog.json"]
    cat = json.load(open(path[0], encoding="utf-8"))
    bad = [p["id"] for p in cat["projects"] if p["system"] in VETOED and not str(p.get("exception", "")).strip()]
    exc = [(p["id"], p["system"]) for p in cat["projects"] if p.get("exception")]
    print(f"{len(exc)} excepciones declaradas: " + ", ".join(f"{i} ({s})" for i, s in exc))
    if bad:
        print(f"✗ {len(bad)} proyectos de sistemas vetados sin `exception`: {', '.join(bad)}")
        return 1
    print("✓ alcance correcto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
