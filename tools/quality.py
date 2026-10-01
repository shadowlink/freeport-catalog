#!/usr/bin/env python3
"""Criba de calidad: asigna a cada proyecto un `tier` a partir de señales objetivas
de GitHub, para que la app muestre por defecto solo lo que está probado.

Niveles
  curado        hecho con mimo y usado por mucha gente: ≥10k descargas de releases,
                o ≥2k descargas con ≥6 meses de vida y ≥3 releases.
  comunidad     funciona y tiene recorrido: ≥500 descargas y ≥2 meses, o ≥6 meses
                con ≥3 releases y ≥200 descargas.
  experimental  todo lo demás: proyectos nuevos, de un solo autor, con pocas
                descargas. No es un juicio: suben solos cuando la gente los usa.

Las descargas acumuladas de releases son la señal principal (nadie las infla a
mano). Edad, nº de releases, colaboradores y palabras de aviso (IA, emulador) se
guardan en `quality_signals` para revisión humana.

Un `tier` fijado a mano se protege con `tier_manual: true` y el script no lo toca.
Los proyectos sin repo de GitHub (descarga directa) quedan en `comunidad` salvo
que se fijen a mano.

    GITHUB_TOKEN=ghp_xxx python3 tools/quality.py catalog.json          # aplica
    GITHUB_TOKEN=ghp_xxx python3 tools/quality.py --report catalog.json # solo informe
"""
import datetime
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://api.github.com"
AI_RE = re.compile(r"vibe.?cod|ai-?(coded|assisted|driven|generated)|claude code|with claude|chatgpt|codex|copilot|gpt-?[45]|qwen|\bllm\b", re.I)
EMU_RE = re.compile(r"\b(interpreter|lle-first|built-in (snes|nes|genesis|cpu) core|lakesnes|emulator core|cycle.?accurate|runs the rom on)\b", re.I)


def gh(url, token, raw=False):
    req = urllib.request.Request(url, headers={
        "User-Agent": "freeport-quality", "Accept": "application/vnd.github+json",
        **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace") if raw else json.load(r)
    except Exception:
        return None


def signals(p, token):
    r = p["repo"]
    if r["host"] != "github":
        return None
    slug = f"{r['owner']}/{r['repo']}"
    info = gh(f"{API}/repos/{slug}", token) or {}
    rels = gh(f"{API}/repos/{slug}/releases?per_page=100", token) or []
    cons = gh(f"{API}/repos/{slug}/contributors?per_page=5&anon=0", token) or []
    md = gh(f"https://raw.githubusercontent.com/{slug}/{info.get('default_branch', 'main')}/README.md", token, raw=True) or ""
    rels = rels if isinstance(rels, list) else []
    now = datetime.datetime.now(datetime.timezone.utc)
    created = info.get("created_at")
    age = (now - datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))).days if created else 0
    return {
        "downloads": sum(a.get("download_count", 0) for x in rels for a in x.get("assets", [])),
        "stars": info.get("stargazers_count", 0),
        "age_days": age,
        "releases": len(rels),
        "contributors": len(cons) if isinstance(cons, list) else 0,
        "ai": bool(AI_RE.search(md) or AI_RE.search(info.get("description") or "")),
        "emu": bool(EMU_RE.search(md)),
        "checked": now.strftime("%Y-%m-%d"),
    }


def tier_for(s):
    dl, age, rel = s["downloads"], s["age_days"], s["releases"]
    if dl >= 10000 or (dl >= 2000 and age >= 180 and rel >= 3):
        return "curado"
    if (dl >= 500 and age >= 60) or (age >= 180 and rel >= 3 and dl >= 200):
        return "comunidad"
    return "experimental"


def main():
    report = "--report" in sys.argv
    path = ([a for a in sys.argv[1:] if not a.startswith("--")] or ["catalog.json"])[0]
    token = os.environ.get("GITHUB_TOKEN")
    cat = json.load(open(path, encoding="utf-8"))
    with ThreadPoolExecutor(8) as ex:
        sigs = list(ex.map(lambda p: signals(p, token), cat["projects"]))
    counts = {"curado": 0, "comunidad": 0, "experimental": 0}
    changed = 0
    for p, s in zip(cat["projects"], sigs):
        if s:
            p["quality_signals"] = s
            auto = tier_for(s)
        else:
            auto = p.get("tier") or "comunidad"
        if p.get("tier_manual"):
            tier = p.get("tier") or auto
        else:
            tier = auto
        if p.get("tier") != tier:
            changed += 1
        p["tier"] = tier
        counts[tier] += 1
    print(f"curado {counts['curado']} · comunidad {counts['comunidad']} · experimental {counts['experimental']} · cambios {changed}")
    if not report:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cat, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
