"""Descarga el modelo v6 (release modelo-v6-e2) y verifica su integridad, sin ejecutarlo."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

# Permite importar "app" al ejecutar: python scripts/download_model.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.ml_service import MODEL_V6  # noqa: E402

RELEASE_URL = f"https://github.com/bupsidu/Healthcare_Analytics_Project/releases/download/{MODEL_V6.release}/"
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[2] / "Modelo" / "artifacts"


def verify_model(directory: Path) -> None:
    """Comprueba tamaño y SHA-256 del .joblib contra los valores fijados en el código."""
    model_path = directory / MODEL_V6.model_filename
    if model_path.stat().st_size != MODEL_V6.model_bytes:
        raise ValueError("La descarga del modelo está incompleta o no es la versión esperada")
    checksum = hashlib.sha256()
    with model_path.open("rb") as model_file:
        for block in iter(lambda: model_file.read(1024 * 1024), b""):
            checksum.update(block)
    if checksum.hexdigest() != MODEL_V6.model_sha256:
        raise ValueError("El SHA-256 del modelo no coincide con el release esperado")
    metadata_path = directory / MODEL_V6.metadata_filename
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("release") != MODEL_V6.release:
            raise ValueError("El metadata no corresponde al release esperado")


def download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "Healthcare-Analytics/0.1"})
    with urlopen(request, timeout=60) as response, destination.open("wb") as output:
        for block in iter(lambda: response.read(1024 * 1024), b""):
            output.write(block)


def download_artifacts(directory: Path) -> None:
    directory = directory.resolve()
    model_path = directory / MODEL_V6.model_filename
    if model_path.exists():
        verify_model(directory)
        print(f"El modelo ya existe y está verificado: {model_path}")
        return

    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=directory) as temporary_dir:
        staging = Path(temporary_dir)
        print(f"Descargando {MODEL_V6.model_filename} (~45 MB)...", flush=True)
        download(RELEASE_URL + MODEL_V6.model_filename, staging / MODEL_V6.model_filename)
        # El metadata normalmente ya viene en Git; solo se baja si falta.
        if not (directory / MODEL_V6.metadata_filename).exists():
            print(f"Descargando {MODEL_V6.metadata_filename}...", flush=True)
            download(RELEASE_URL + MODEL_V6.metadata_filename, staging / MODEL_V6.metadata_filename)
        verify_model(staging)
        for path in staging.iterdir():
            target = directory / path.name
            if target.exists():
                raise FileExistsError(f"No se sobrescribirá el archivo existente: {target}")
            path.rename(target)
    print(f"Descarga completa; SHA-256 verificado. Artefactos en {directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    try:
        download_artifacts(args.directory)
    except Exception as exc:
        parser.exit(1, f"No fue posible preparar el modelo: {exc}\n")
