#!/usr/bin/env python3
"""Barrido de GitHub: repos recientes de recomps/ports que publiquen binarios y NO
estén en el catálogo. Complementa a discover.py (listas de la comunidad) con la
API de búsqueda de GitHub; ajusta QUERIES y las fechas `pushed:>` a la época.

Uso:
    GITHUB_TOKEN=ghp_xxx python3 tools/sweep.py candidatos.json   # informe por stderr
"""
import json, os, re, sys, time, urllib.request, urllib.parse
TOKEN=os.environ["GITHUB_TOKEN"]
H={"Authorization":f"Bearer {TOKEN}","Accept":"application/vnd.github+json","User-Agent":"freeport-sweep"}
def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=H),timeout=30) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403,429): time.sleep(20); continue
            return None
        except Exception: time.sleep(3)
    return None
cat=json.load(open('catalog.json'))
have={(p['repo']['owner']+'/'+p['repo']['repo']).lower() for p in cat['projects']}
QUERIES=[
 'recomp in:name pushed:>2026-04-01','recompiled in:name pushed:>2026-04-01','"static recompilation" pushed:>2026-04-01',
 'N64Recomp pushed:>2026-04-01','psxrecomp pushed:>2026-04-01','snesrecomp pushed:>2026-04-01','XenonRecomp pushed:>2026-04-01',
 'RecompOne pushed:>2026-04-01','"native PC port" pushed:>2026-04-01','"PC port" decomp pushed:>2026-04-01',
 'topic:recompilation pushed:>2026-04-01','topic:decompilation "port" pushed:>2026-04-01','"pc port" n64 pushed:>2026-04-01',
 '"pc port" playstation pushed:>2026-04-01','"pc port" gamecube pushed:>2026-04-01','"pc port" snes pushed:>2026-04-01',
 'libultraship pushed:>2026-04-01','"bring your own rom" pushed:>2026-04-01','"decompilation" "native" port game pushed:>2026-06-01',
 'gbarecomp OR gbcrecomp OR nesrecomp pushed:>2026-04-01','dsrecomp OR ndsrecomp OR psprecomp pushed:>2026-04-01',
]
repos={}
for q in QUERIES:
    for page in (1,2):
        d=get(f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort=updated&order=desc&per_page=100&page={page}")
        time.sleep(2.2)
        if not d or 'items' not in d: break
        for it in d['items']:
            slug=it['full_name']
            if slug.lower() in have: continue
            repos.setdefault(slug,{'slug':slug,'desc':it.get('description') or '','stars':it['stargazers_count'],'pushed':it['pushed_at'],'fork':it['fork'],'queries':[]})
            repos[slug]['queries'].append(q.split(' pushed')[0])
        if len(d['items'])<100: break
print(f"# {len(repos)} repos candidatos tras búsqueda", file=sys.stderr)
BIN=re.compile(r'\.(zip|tar\.gz|tar\.xz|7z|rar|appimage|exe|deb|dmg)$',re.I)
BAD=re.compile(r'source|symbols|sdk|toolchain|\.sha256$|\.txt$|\.json$|\.md$|\.apk$',re.I)
out=[]
for i,(slug,r) in enumerate(sorted(repos.items(),key=lambda x:-x[1]['stars'])):
    rel=get(f"https://api.github.com/repos/{slug}/releases?per_page=3")
    if not rel or not isinstance(rel,list): continue
    assets=[a['name'] for rr in rel for a in rr.get('assets',[]) if BIN.search(a['name']) and not BAD.search(a['name'])]
    if not assets: continue
    r['latest']=rel[0]['tag_name']; r['prerelease']=rel[0]['prerelease']; r['released']=rel[0]['published_at']; r['assets']=sorted(set(assets))[:8]
    out.append(r)
    print(f"  + {slug} ★{r['stars']} {r['latest']} :: {r['desc'][:90]}", file=sys.stderr)
json.dump(out,open(sys.argv[1],'w'),indent=1,ensure_ascii=False)
print(f"# {len(out)} con binario publicado", file=sys.stderr)
