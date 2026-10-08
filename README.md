# autocrop

MVP local de recorte de fotografías deportivas.

El recorrido técnico, las decisiones y los resultados de las etapas 01–06 están
en [Historial técnico](docs/historial-tecnico.md). Los contratos y comandos de
verificación originales están en `plans/`.

## Entorno

- Python >= 3.12
- Crear entorno virtual:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

## Tests

```bash
.venv/bin/python -m pytest
```

## Uso

```bash
python -m app.cli --input ./fotos --output ./output
# Opcional: python -m app.cli --input ./fotos --output ./output --ratio 3:2 --margin 0.15
```

- `--input` (requerido): carpeta existente con JPEG (no recursivo; `.jpg`/`.jpeg`
  insensibles a mayúsculas). Si no existe o no es directorio, falla sin crear nada.
- `--output` (requerido): se crea si no existe; guarda un JPEG recortado
  (`quality=95`) por foto con el mismo nombre base.
- `--ratio W:H` (opcional): proporción fija para todo el lote, p. ej. `3:2`.
  Ausente: automática por imagen (3:2 horizontal, 2:3 vertical, 1:1 cuadrada).
- `--margin F` (opcional, default `0.15`): margen finito `>= 0` alrededor del sujeto.
- El detector es `yolo11n.pt` del directorio actual con `confidence=0.25`.
- Fotos sin persona, sin recorte válido o ilegibles se copian sin modificar a
  `output/review/` con el motivo en `output/review.log`; el lote termina en `0`.
- Archivos no-JPEG se omiten con aviso por consola, sin ir a `output/review/` ni al log.

```python
from pathlib import Path
from PIL import Image, ImageOps
from app.detector import YOLODetector
from app.subject import select_subject
from app.crop import calculate_crop

detector = YOLODetector(Path("yolo11n.pt"), confidence=0.25)
image = ImageOps.exif_transpose(Image.open("foto.jpg"))  # el procesador (etapa 03) asume RGB + orientación EXIF
boxes = detector.detect_people(image.convert("RGB"))
subject = select_subject(boxes)
if subject is None:
    print("sin personas: gestionado por app.processor (etapa 03)")
else:
    res = calculate_crop(image.width, image.height, subject, (1, 1), 0.15)
```

## Pesos del modelo

- Validación con **YOLO11n de detección preentrenado en COCO** (`yolo11n.pt`),
  variante pequeña elegida para correr en CPU, no por ser la última disponible.
- Descargar explícitamente desde una fuente oficial de Ultralytics antes de
  ejecutar; el adaptador **no** descarga pesos ni acepta nombres remotos: una
  ruta inexistente produce `FileNotFoundError`.
- Ultralytics y sus pesos oficiales usan licencia **AGPL-3.0**; revisar sus
  condiciones antes de distribuir el producto.

```bash
# ejemplo de obtención manual (verificar URL/licencia vigente en docs oficiales)
curl -L -o yolo11n.pt https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
```

## Docker

El contenedor persistente se llama `autocrop` y ejecuta el mismo procesador en
CPU. Requiere Docker Engine, el plugin Compose con soporte para
`bind.create_host_path: false`, y `yolo11n.pt` en la raíz del proyecto. El
build copia ese archivo a la imagen; falla si falta. Las dependencias se
descargan durante el build, pero el procesador no descarga pesos al ejecutarse.

Desde la raíz del repositorio, con fotos JPEG en `./fotos`:

```bash
export AUTOCROP_UID=$(id -u) AUTOCROP_GID=$(id -g)
mkdir -p output
docker compose up -d --build
docker exec -it autocrop autocrop --help
docker exec -it autocrop autocrop --input /input --output /output
```

Atajo portable: `./autocrop-run [input] [output] [opciones]` hace lo mismo
resolviendo rutas absolutas, creando la salida si falta y levantando el
contenedor si hace falta (defaults `./fotos` `./output`; acepta `--ratio` y
`--margin` al final).

Para usar otras carpetas existentes, definir rutas absolutas **antes** de crear
el contenedor. La carpeta de salida debe existir; Compose no crea ninguno de
los dos directorios si falta. Por ejemplo:

```bash
export AUTOCROP_INPUT_DIR=/ruta/absoluta/a/fotos
export AUTOCROP_OUTPUT_DIR=/ruta/absoluta/a/salida
export AUTOCROP_UID=$(id -u) AUTOCROP_GID=$(id -g)
mkdir -p "$AUTOCROP_OUTPUT_DIR"
docker compose up -d --build
docker exec -it autocrop autocrop --input /input --output /output --ratio 3:2 --margin 0.15
```

`docker exec` necesita un comando después del nombre del contenedor: el
segundo `autocrop` es el ejecutable de la CLI. `--ratio` y `--margin` son
opcionales y tienen los mismos valores por defecto que `python -m app.cli`.
La entrada se monta en `/input` en modo solo lectura y la salida en `/output`
con escritura. Cada JPEG recortado aparece en la carpeta de salida del host;
los casos que requieren revisión aparecen en `review/`, con su motivo en
`review.log`. Los archivos nuevos pertenecen al UID/GID exportado.

Para cambiar las carpetas montadas, modificar las variables y ejecutar
`docker compose up -d` de nuevo para recrear el contenedor. Para detenerlo,
ejecutar `docker compose down`. Si la entrada no existe, el build no encuentra
los pesos, o se indican rutas conflictivas, el comando falla con un error;
la [etapa 05](plans/05-seguridad-rutas/plan.md) documenta la protección de
originales. La selección por mayor área y la calidad de composición siguen
siendo las evaluadas en la [etapa 04](plans/04-evaluacion/registro.md).

### Versiones de la imagen

La imagen local revisada el 2026-10-08 (`autocrop:latest`, ID
`sha256:807d49678be764d4c6a177cacf4abe2a2a1841eb99202dd9949aea7ee1cd008e`)
contiene Python 3.12.15, PyTorch 2.14.1+cpu, torchvision 0.29.1+cpu,
Ultralytics 8.4.174 y Pillow 12.3.0. Se comprobó que
`torch.version.cuda is None`. Para consultar la imagen disponible en otro
equipo:

```bash
docker image inspect autocrop:latest --format '{{.Id}} {{.Created}}'
docker run --rm --network none autocrop:latest python -m pip list --format=freeze
docker run --rm --network none autocrop:latest python -c 'import sys, torch; print(sys.version.split()[0], torch.__version__, torch.version.cuda)'
```

Estas son versiones **observadas**, no fijadas para builds futuros. El
Dockerfile usa `python:3.12-slim`, instala bibliotecas del sistema desde los
repositorios vigentes e instala paquetes Python sin versiones exactas. El
índice CPU asegura la variante de PyTorch, pero puede ofrecer otra versión.
Un `docker compose up -d --build` posterior puede cambiar dependencias y
resultados. Para repetir la instalación con las mismas versiones habrá que
fijar el digest de la base, las dependencias directas y transitivas, y las
bibliotecas del sistema; esa fijación todavía no forma parte de la imagen.
