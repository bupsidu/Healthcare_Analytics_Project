"""
Empaqueta los archivos del release del modelo v12 para subirlos a GitHub Releases.

Lee `artifacts/release_manifest_v12.json`, copia los archivos a una carpeta
temporal y verifica el SHA-256 de cada uno. La carpeta resultante se sube
manualmente a GitHub Releases.

Por qué no se guarda el paquete en el repositorio: el modelo pesa 143 MB y ya
existe en `models/`. Duplicarlo no aporta nada y el `.gitignore` lo excluiría
de todos modos.

Uso:
    python3 src/serving/empaquetar_release.py
    python3 src/serving/empaquetar_release.py --destino ~/Desktop/release_v12

Salida:
    <destino>/  con los 4 archivos + el manifiesto
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
MANIFIESTO = BASE / "artifacts" / "release_manifest_v12.json"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--destino",
        default=str(Path.home() / "Desktop" / "release_modelo_v12"),
        help="Carpeta donde se armará el paquete (se crea si no existe)",
    )
    args = ap.parse_args()

    if not MANIFIESTO.exists():
        raise SystemExit(f"No se encontró el manifiesto: {MANIFIESTO}")

    man = json.loads(MANIFIESTO.read_text(encoding="utf-8"))
    destino = Path(args.destino).expanduser().resolve()
    destino.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"Empaquetando release: {man['release']}")
    print(f"Destino: {destino}")
    print("=" * 70)

    total = 0
    ok = True
    for a in man["archivos"]:
        origen = (BASE / a["origen"]).resolve() if not Path(a["origen"]).is_absolute() \
            else Path(a["origen"])
        # El manifiesto guarda rutas relativas al repositorio
        if not origen.exists():
            origen = (BASE.parent / a["origen"]).resolve()

        if not origen.exists():
            print(f"  ✗ {a['nombre']}: no se encontró en {a['origen']}")
            ok = False
            continue

        # Verificar integridad antes de copiar
        h = hashlib.sha256(origen.read_bytes()).hexdigest()
        if h != a["sha256"]:
            print(f"  ✗ {a['nombre']}: SHA-256 no coincide")
            print(f"      esperado: {a['sha256']}")
            print(f"      obtenido: {h}")
            ok = False
            continue

        shutil.copy2(origen, destino / a["nombre"])
        mb = origen.stat().st_size / 1024 / 1024
        total += origen.stat().st_size
        print(f"  ✓ {a['nombre']:38} {mb:>7.1f} MB")

    # Copiar el manifiesto junto al paquete
    shutil.copy2(MANIFIESTO, destino / MANIFIESTO.name)
    print(f"  ✓ {MANIFIESTO.name:38} (manifiesto)")

    print("-" * 70)
    if ok:
        print(f"  Paquete listo: {len(man['archivos'])} archivos, {total/1024/1024:.1f} MB")
        print(f"\n  Subir a GitHub Releases:")
        print(f"    1. Ir a https://github.com/bupsidu/Healthcare_Analytics_Project/releases/new")
        print(f"    2. Tag: {man['release']}")
        print(f"    3. Título: Modelo {man['release']}")
        print(f"    4. Adjuntar los {len(man['archivos'])} archivos de: {destino}")
    else:
        print("  ⚠ Hubo errores; el paquete está incompleto")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
