"""
Genera el mapa tecnológico como PNG con logos oficiales y CONEXIONES reales.

Diseño: diagrama de capas donde las tecnologías están agrupadas en contenedores
y las flechas muestran cómo se comunican, con el protocolo sobre cada conexión.

Cada conexión corresponde a código o configuración real del repositorio:
  Navegador    → React        : HTML/CSS/JS servido por Vite
  React        → FastAPI      : HTTP/JSON + Bearer JWT (axios)
  FastAPI      → PostgreSQL   : SQLAlchemy 2.0 + psycopg2
  FastAPI      → Open-Meteo   : HTTPS (requests)
  Pipeline     → FastAPI      : artefacto .joblib cargado en memoria
  DEIS/MINSAL  → Pipeline     : archivos CSV (carga manual)
  Pipeline     → PostgreSQL   : carga de demanda histórica por SQL

Uso:
    python3 docs/uml/generar_mapa_tecnologico.py
"""

from __future__ import annotations

import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parent
LOGOS = BASE / "logos"
HTML = BASE / "_mapa.html"
OUT = BASE / "png" / "mapa_tecnologico.png"

# (carpeta_svg, etiqueta, color_hex)
CAPAS = {
    "interfaz": [
        ("react", "React 18", None),
        ("vite", "Vite 5", None),
        ("tailwindcss", "Tailwind 3", None),
        ("lucide", "Lucide", None),
        ("axios", "Axios", None),
    ],
    "servidor": [
        ("fastapi", "FastAPI", None),
        ("python", "Python 3.13", None),
        ("sqlalchemy", "SQLAlchemy 2.0", None),
        ("pydantic", "Pydantic", None),
    ],
    "datos": [
        ("postgresql", "PostgreSQL", None),
    ],
    "ml": [
        ("scikitlearn", "scikit-learn 1.7", None),
        ("pandas", "pandas 2.3", None),
        ("numpy", "NumPy 2.3", None),
        ("jupyter", "Jupyter", None),
    ],
    "externos": [
        ("openmeteo", "Open-Meteo", "#00A3E0"),
        ("deis", "DEIS / MINSAL", "#B91C1C"),
    ],
    "herramientas": [
        ("git", "Git", None),
        ("github", "GitHub", None),
    ],
}

INICIALES = {
    "UV": ("Uvicorn", "#499848"),
    "RC": ("Recharts", "#22B5BF"),
    "JWT": ("python-jose", "#D63AFF"),
    "BC": ("bcrypt", "#338FCC"),
    "PG": ("pgAdmin", "#336791"),
    "JL": ("joblib", "#F7931E"),
    "PS": ("psycopg2", "#2E6DA4"),
}


def color_de(name: str) -> str:
    f = LOGOS / f"{name}.svg"
    if not f.exists():
        return "#6B7280"
    m = re.search(r'fill="(#[0-9A-Fa-f]{6})"', f.read_text())
    return m.group(1) if m else "#6B7280"


def icono(name: str, label: str, color: str | None, size: int = 58) -> str:
    """HTML de un icono: SVG oficial si existe, si no cuadrado con iniciales."""
    f = LOGOS / f"{name}.svg"
    if f.exists():
        return (
            f'<div class="item"><img src="logos/{name}.svg" style="width:{size}px;height:{size}px" alt="{label}">'
            f'<div class="lbl">{label}</div></div>'
        )
    c = color or "#6B7280"
    ini = name[:2].upper()
    return (
        f'<div class="item"><div class="ini" style="width:{size}px;height:{size}px;background:{c};'
        f'font-size:{int(size*0.34)}px">{ini}</div><div class="lbl">{label}</div></div>'
    )


def construir_html() -> str:
    def fila(clave: str) -> str:
        return "".join(icono(n, lbl, col) for n, lbl, col in CAPAS[clave])

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; }}
body {{ margin:0; padding:34px; background:#fff; width:1240px;
       font-family:-apple-system,'Segoe UI',Roboto,sans-serif; }}
.capa {{ border:2px solid; border-radius:18px; padding:14px 20px 16px; }}
.capa .tit {{ font-size:15px; font-weight:700; letter-spacing:.3px;
             text-transform:uppercase; margin-bottom:10px; }}
.fila {{ display:flex; gap:22px; flex-wrap:wrap; }}
.item {{ display:flex; flex-direction:column; align-items:center; width:96px; }}
.item img {{ display:block; }}
.ini {{ border-radius:14px; display:flex; align-items:center; justify-content:center;
        color:#fff; font-weight:700; }}
.lbl {{ font-size:12px; color:#1F2937; margin-top:6px; text-align:center; line-height:1.25; }}
.flecha {{ display:flex; flex-direction:column; align-items:center; margin:7px 0; }}
.flecha .linea {{ width:3px; height:24px; background:#94A3B8; }}
.flecha .prot {{ font-size:11.5px; color:#475569; background:#F1F5F9;
                 border:1px solid #CBD5E1; border-radius:11px; padding:3px 12px;
                 margin:3px 0; white-space:nowrap; font-weight:600; }}
.flecha .tri {{ width:0; height:0; border-left:9px solid transparent;
                border-right:9px solid transparent; border-top:12px solid #94A3B8; }}
.ext {{ display:flex; gap:20px; }}
.col {{ display:flex; flex-direction:column; flex:1; }}
.fila-sec {{ display:flex; gap:18px; align-items:flex-start; }}
</style></head><body>

<!-- Interfaz -->
<div class="capa" style="background:#EAF9FE;border-color:#0891B2">
  <div class="tit" style="color:#0891B2">Capa de presentación</div>
  <div class="fila">{fila('interfaz')}</div>
</div>

<div class="flecha">
  <div class="linea"></div><div class="prot">HTTP / JSON · Bearer JWT</div>
  <div class="linea"></div><div class="tri"></div>
</div>

<!-- Servidor -->
<div class="capa" style="background:#E8F5F4;border-color:#00796B">
  <div class="tit" style="color:#00796B">Capa de aplicación</div>
  <div class="fila">{fila('servidor')}</div>
</div>

<!-- Servidor hacia datos / externos / artefactos -->
<div class="fila-sec">
  <div class="col">
    <div class="flecha">
      <div class="linea"></div><div class="prot">SQLAlchemy + psycopg2</div>
      <div class="linea"></div><div class="tri"></div>
    </div>
    <div class="capa" style="background:#EEF2FF;border-color:#4169E1">
      <div class="tit" style="color:#4169E1">Capa de persistencia</div>
      <div class="fila">{fila('datos')}</div>
    </div>
  </div>

  <div class="col">
    <div class="flecha">
      <div class="linea"></div><div class="prot">HTTPS</div>
      <div class="linea"></div><div class="tri"></div>
    </div>
    <div class="capa" style="background:#F0FDFA;border-color:#0EA5A0">
      <div class="tit" style="color:#0A7A76">Servicios externos</div>
      <div class="fila">{fila('externos')}</div>
    </div>
  </div>

  <div class="col">
    <div class="flecha">
      <div class="linea"></div><div class="prot">joblib (memoria)</div>
      <div class="linea"></div><div class="tri"></div>
    </div>
    <div class="capa" style="background:#FFF7ED;border-color:#EA580C">
      <div class="tit" style="color:#C2410C">Artefacto del modelo</div>
      <div class="fila">
        {icono('JL', 'modelo v12 .joblib', '#F7931E')}
      </div>
    </div>
  </div>
</div>

<div class="flecha">
  <div class="linea"></div><div class="prot">entrena · CSV de DEIS</div>
  <div class="linea"></div><div class="tri"></div>
</div>

<!-- Pipeline -->
<div class="capa" style="background:#FFF4E6;border-color:#C2410C">
  <div class="tit" style="color:#C2410C">Procesamiento y entrenamiento (fuera de línea)</div>
  <div class="fila">{fila('ml')}</div>
</div>

<!-- Herramientas -->
<div style="margin-top:20px;display:flex;gap:16px;align-items:center;
            border-top:2px dashed #CBD5E1;padding-top:16px">
  <div style="font-size:13px;font-weight:700;color:#64748B;min-width:150px">Transversal</div>
  <div class="fila" style="gap:18px">{fila('herramientas')}
    {icono('GITFLOW', 'Ramas y releases', '#64748B')}
  </div>
</div>

</body></html>"""


def main() -> None:
    html = construir_html()
    HTML.write_text(html, encoding="utf-8")
    print(f"  HTML generado: {HTML.name}")

    import subprocess
    import glob

    # puppeteer del caché de npx (ya instalado por mermaid-cli)
    cands = glob.glob(str(pathlib.Path.home() / ".npm/_npx/*/node_modules/puppeteer"))
    if not cands:
        raise SystemExit("No se encontró puppeteer. Ejecutá: npx @mermaid-js/mermaid-cli --version")
    pp = cands[0]

    script = BASE / "_shot.cjs"
    script.write_text(
        f"""const puppeteer = require('{pp}');
const path = require('path');
(async () => {{
  const b = await puppeteer.launch({{args:['--no-sandbox']}});
  const p = await b.newPage();
  await p.setViewport({{width:1240,height:900,deviceScaleFactor:2}});
  await p.goto('file://' + path.resolve('_mapa.html'), {{waitUntil:'networkidle0'}});
  await p.screenshot({{path:'png/mapa_tecnologico.png', fullPage:true}});
  await b.close();
  console.log('ok');
}})();""",
        encoding="utf-8",
    )
    r = subprocess.run(["node", str(script)], cwd=BASE, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"Error al capturar: {r.stderr}")
    script.unlink()
    HTML.unlink()

    from PIL import Image
    img = Image.open(OUT)
    print(f"  ✓ {OUT.relative_to(BASE.parent.parent)}  {img.size[0]}x{img.size[1]}px")


if __name__ == "__main__":
    main()
