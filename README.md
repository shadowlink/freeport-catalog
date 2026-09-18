# freeport-catalog

Catálogo curado de juegos para **[Freeport](https://github.com/shadowlink/freeport)**,
el launcher de escritorio para *ports nativos* y *recompilaciones estáticas* de
juegos de consola a PC.

Este repo es la **fuente de la verdad** del catálogo. La app Freeport descarga
`catalog.json` desde aquí (vía `raw.githubusercontent.com`) y lo cachea; si no hay
red, usa una copia embebida en el binario como *fallback* offline.

## `catalog.json`

Un único manifiesto con `systems` (consolas) y `projects` (juegos). Cada proyecto
declara su repo de GitHub, `asset_rules` (regex por plataforma para elegir el
binario correcto), modo de ROM, metadatos (año/desarrollador/género/wiki) y un
bloque `cached` que rellena la CI.

**La app nunca distribuye ROMs.** Solo lista proyectos que publican binario; el
usuario aporta su propia copia legal del juego cuando el port la requiere.

## Mantenimiento automático

`.github/workflows/update-catalog.yml` ejecuta `tools/probe.py` **a diario**: para
cada proyecto consulta sus GitHub Releases y actualiza los campos `cached`
(`latest_tag`, `published_at`, `platforms`) — que la app usa para pre-filtrar por
plataforma y avisar de actualizaciones sin machacar la API de GitHub por juego.
Si algo cambia, se commitea automáticamente.

```bash
# manual (opcional)
GITHUB_TOKEN=ghp_xxx python3 tools/probe.py catalog.json
```

`tools/discover.py` cruza las listas de la comunidad con repos que publican
binarios, como ayuda para descubrir candidatos nuevos.

## Varias versiones del mismo juego (`game_id`)

Cuando dos proyectos portan el **mismo juego** (Zelda64Recomp y 2Ship son ambos
Majora's Mask), la app los agrupa en **una sola tarjeta** con selector de versión
en la ficha. La clave es `game_id`: por defecto el *slug* de `original_game`
(`tools/groups.py` lo rellena y lista los grupos). Edítalo a mano si el nombre
coincide pero el juego no, o para juntar un remaster con el original. Un
`preferred: true` opcional marca la versión mostrada por defecto; si falta, la app
prefiere la build nativa de la plataforma y después la release más reciente.

```bash
python3 tools/groups.py catalog.json          # rellena game_id que falten + informe
python3 tools/groups.py --check catalog.json  # falla si algún proyecto no lo tiene
```

## Añadir un juego

Edita `catalog.json` (añade un objeto a `projects`, con su `game_id`) y abre un PR.
La CI rellenará su `cached` en la siguiente ejecución.
