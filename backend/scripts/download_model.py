"""Descarga los tres artefactos del release modelo-v1 sin ejecutar el modelo."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen


RELEASE_URL = "https://github.com/bupsidu/Healthcare_Analytics_Project/releases/download/modelo-v1/"
MODEL_NAME = "model_rf_respiratorio.joblib"
EXPECTED_SHA256 = "f6ff542d1401256c979c4960dcc3603b24a6965e8d321f1c07a9fb1f31c8ebb1"
ARTIFACT_NAMES = ("features.json", "model_metadata.json", MODEL_NAME)
DEFAULT_DIRECTORY = Path(__file__).resolve().parents[2] / "Modelo" / "artifacts"


def verify_artifacts(directory: Path) -> None:
    features = json.loads((directory / "features.json").read_text(encoding="utf-8"))
    metadata = json.loads((directory / "model_metadata.json").read_text(encoding="utf-8"))
    if not isinstance(features, list) or not all(isinstance(name, str) for name in features):
        raise ValueError("features.json debe ser una lista de nombres")
    if len(features) != 20 or len(set(features)) != 20 or metadata.get("features") != features:
        raise ValueError("Las features y el metadata no coinciden")
    if metadata.get("model_name") != MODEL_NAME or metadata.get("release") != "modelo-v1":
        raise ValueError("El metadata no corresponde al release solicitado")
    if metadata.get("model_sha256") != EXPECTED_SHA256:
        raise ValueError("El hash publicado no corresponde al release verificado")
    model_path = directory / MODEL_NAME
    if model_path.stat().st_size != metadata.get("model_bytes"):
        raise ValueError("La descarga del modelo está incompleta")
    checksum = hashlib.sha256()
    with model_path.open("rb") as model_file:
        for block in iter(lambda: model_file.read(1024 * 1024), b""):
            checksum.update(block)
    if checksum.hexdigest() != EXPECTED_SHA256:
        raise ValueError("El SHA-256 del modelo no coincide con el release")


def download_artifacts(directory: Path) -> None:
    directory = directory.resolve()
    existing = [name for name in ARTIFACT_NAMES if (directory / name).exists()]
    if len(existing) == len(ARTIFACT_NAMES):
        verify_artifacts(directory)
        print(f"Los artefactos ya existen y están verificados: {directory}")
        return
    if existing:
        raise FileExistsError("Ya hay artefactos parciales en la carpeta; revíselos antes de volver a descargar")

    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=directory) as temporary_dir:
        staging = Path(temporary_dir)
        for name in ARTIFACT_NAMES:
            print(f"Descargando {name}...", flush=True)
            request = Request(RELEASE_URL + name, headers={"User-Agent": "Healthcare-Analytics/0.1"})
            with urlopen(request, timeout=30) as response, (staging / name).open("wb") as output:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    output.write(block)
        verify_artifacts(staging)
        for name in ARTIFACT_NAMES:
            target = directory / name
            if target.exists():
                raise FileExistsError(f"No se sobrescribirá el archivo existente: {target}")
            (staging / name).rename(target)
    print(f"Descarga completa; SHA-256 verificado. Artefactos en {directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    try:
        download_artifacts(args.directory)
    except Exception as exc:
        parser.exit(1, f"No fue posible preparar los artefactos: {exc}\n")
