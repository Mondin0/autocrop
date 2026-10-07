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

```python
from pathlib import Path
from PIL import Image, ImageOps
from app.detector import YOLODetector
from app.subject import select_subject
from app.crop import calculate_crop

detector = YOLODetector(Path("yolo11n.pt"), confidence=0.25)
image = ImageOps.exif_transpose(Image.open("foto.jpg"))  # el futuro procesador (etapa 03, sin definir) asumirá RGB + orientación EXIF
boxes = detector.detect_people(image.convert("RGB"))
subject = select_subject(boxes)
if subject is None:
    print("sin personas: reservado para output/review/ en la etapa 03")
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
