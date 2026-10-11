# Registro — etapa 08

## Implementación

- Archivos: `Dockerfile`, `compose.yaml`, `compose.hub.yaml`, `README.md`, `tests/test_docker_hub.py` y `.plans/v1/PLAN.md`.
- Pruebas primero: `.venv/bin/python -m pytest tests/test_docker_hub.py -q` falló inicialmente en los tres contratos aún no implementados.
- `.venv/bin/python -m pytest tests/test_docker_hub.py tests/test_compose.py tests/test_compose_nodata.py tests/test_packaging.py -q` → 40 passed.
- `AUTOCROP_IMAGE=example/autocrop:0.1.0 docker compose -f compose.yaml -f compose.hub.yaml config --quiet` → 0.
- `docker pull rustfs/rustfs:1.0.1-glibc` → descargado; digest `sha256:87763ed4dcb2bed3fc52cbf6cb7d865411e085b0b952dc78e50dffa9ece0ed9e`.
- `docker buildx build --platform linux/amd64 --load -t autocrop:hub-check .` → 0; `pip check` durante build → `No broken requirements found`.
- `docker run --rm --network none autocrop:hub-check python -c 'import app, torch, cv2; ...'` → 0; Torch `2.14.1+cpu`, CUDA `None`, OpenCV `5.0.0`; tamaño local `2,540,746,785` bytes.
- `docker buildx build --check --platform linux/amd64,linux/arm64 .` → 0, sin warnings.
- El índice oficial de wheels PyTorch CPU contiene wheels cp312 manylinux aarch64 para Torch 2.14.1 y torchvision 0.29.1; esto confirma disponibilidad del wheel, no sustituye el build de la imagen.
- `.venv/bin/python -m pytest` → 461 passed, 1 skipped y 4 errores de setup: falta la fixture `page` de `pytest-playwright` en el entorno. No hubo fallos de aserción.
- El build real `linux/arm64 --load` se detuvo en el primer `RUN` con `exec format error`: Docker no tiene emulación arm64 configurada. No se publicó la imagen. Se omitió `opencv-python-headless` porque Ultralytics declara `opencv-python` y la sustitución rompe `pip check`.

## Revisión

- F1–F4 y T1 comprobados por tests, configuración Compose y README; amd64 construye y pasa `pip check` e imports.
- T2 queda parcialmente pendiente: falta probar build real y smoke de arm64 por ausencia de QEMU/binfmt. El `--check` multiarch es estático.
- La suite completa queda pendiente de repetir con `pytest-playwright` disponible para que exista la fixture `page`.
- No se hizo push: el namespace/credencial de Docker Hub no está configurado; el README deja el namespace como variable a reemplazar.
- Hallazgo pendiente, criterio T2: verificar build real de `linux/arm64` y smoke/imports/`pip check` en un host arm64 o builder con emulación antes de cerrar la etapa.
