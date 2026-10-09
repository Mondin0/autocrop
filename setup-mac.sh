#!/usr/bin/env bash
# venv portable en Mac Apple Silicon (etapa 07).
# Uso: ./setup-mac.sh [--dev]
#   Por defecto instala runtime (.); con --dev instala .[dev] para correr tests.
# Verifica python3.12 (sin auto-instalar), crea .venv, instala el proyecto,
# comprueba el hash de yolo11n.pt, corre --help y un humo sintético en
# temporales (ruta review, con una imagen generada, sin originales).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

EXPECTED_HASH="0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    echo "Usage: ./setup-mac.sh [--dev]"
    exit 0
fi

if ! command -v python3.12 >/dev/null 2>&1; then
    echo "error: python3.12 no encontrado." >&2
    echo "Instalalo con Homebrew (brew install python@3.12) o desde https://www.python.org/downloads/ y volvé a correr ./setup-mac.sh" >&2
    exit 1
fi

is_python312() {
    "$1" -B -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1
}
if ! is_python312 python3.12; then
    echo "error: python3.12 no ejecuta Python 3.12. Instalalo con brew install python@3.12 o desde https://www.python.org/downloads/" >&2
    exit 1
fi

if [ ! -f "yolo11n.pt" ]; then
    echo "error: yolo11n.pt no encontrado en $ROOT; descargalo de una fuente oficial de Ultralytics (ver README) y volvé a correr ./setup-mac.sh" >&2
    exit 1
fi
if command -v shasum >/dev/null 2>&1; then
    ACTUAL_HASH="$(shasum -a 256 yolo11n.pt | awk '{print $1}')"
else
    ACTUAL_HASH="$(sha256sum yolo11n.pt | awk '{print $1}')"
fi
if [ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]; then
    echo "error: el hash de yolo11n.pt difiere del esperado ($EXPECTED_HASH); descargalo de nuevo de una fuente oficial" >&2
    exit 1
fi

if [ ! -e ".venv" ] && [ ! -L ".venv" ]; then
    python3.12 -m venv .venv
fi
if [ ! -f ".venv/pyvenv.cfg" ] || [ ! -x ".venv/bin/python" ] || ! is_python312 .venv/bin/python; then
    echo "error: .venv incompatible o incompleto; se requiere Python 3.12. No se modificó el entorno; revisalo antes de volver a correr ./setup-mac.sh" >&2
    exit 1
fi
# -B evita escribir bytecode al comprobar un entorno que podría estar incompleto.
if ! .venv/bin/python -B -m pip --version >/dev/null 2>&1; then
    echo "error: .venv incompleto: pip no disponible. No se modificó el entorno; revisalo antes de volver a correr ./setup-mac.sh" >&2
    exit 1
fi
if [ "${1:-}" = "--dev" ]; then
    .venv/bin/python -m pip install -e '.[dev]'
else
    .venv/bin/python -m pip install .
fi

.venv/bin/autocrop --help

SMOKE="$(mktemp -d)"
trap 'rm -rf "$SMOKE"' EXIT
mkdir -p "$SMOKE/in" "$SMOKE/out"
.venv/bin/python - "$SMOKE/in/blank.jpg" <<'EOF'
import sys
from PIL import Image
Image.new("RGB", (640, 480), "white").save(sys.argv[1], "JPEG")
EOF
OUT="$(.venv/bin/autocrop --input "$SMOKE/in" --output "$SMOKE/out")"
echo "$OUT"
echo "$OUT" | grep -q "1 processed" || { echo "error: humo sintético sin '1 processed'" >&2; exit 1; }
echo "$OUT" | grep -q "1 review" || { echo "error: humo sintético sin '1 review'" >&2; exit 1; }
[ -f "$SMOKE/out/review/blank.jpg" ] || { echo "error: humo sintético sin review/blank.jpg" >&2; exit 1; }
echo "setup-mac OK"
