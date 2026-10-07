# autocrop

MVP local de recorte de fotografías deportivas.

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
python -m app.cli --input ./fotos --output ./output [--ratio 3:2] [--margin 0.15]
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
