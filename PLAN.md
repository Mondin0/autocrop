Quiero construir un MVP local en Python para automatizar el recorte de fotografías deportivas, especialmente maratones y eventos donde suele existir un sujeto principal claramente identificable.

## Problema

Un fotógrafo puede volver de una maratón con 5.000–10.000 fotografías.

El trabajo manual más costoso es:

1. identificar al sujeto principal;
2. recortar la fotografía;
3. centrar/componer al sujeto correctamente;
4. repetir esto miles de veces antes de terminar el trabajo en Lightroom.

El MVP debe resolver inicialmente SOLO el recorte automático.

No implementar todavía:
- clasificación por foco/nitidez;
- eliminación de duplicados;
- edición de exposición/color;
- interfaz gráfica;
- integración completa con Lightroom;
- modelos propios.

## Objetivo del MVP

Crear una CLI que:

1. reciba una carpeta de imágenes;
2. detecte personas usando YOLO mediante `ultralytics`;
3. determine cuál es el sujeto principal;
4. obtenga su bounding box;
5. calcule un crop alrededor del sujeto;
6. mantenga una relación de aspecto configurable;
7. intente centrar al sujeto;
8. agregue un margen configurable;
9. nunca permita que el crop salga de los límites de la imagen;
10. genere una imagen recortada en una carpeta de salida;
11. nunca modifique las imágenes originales.

Inicialmente trabajar con JPEG para simplificar las pruebas.

## Stack

Usar:

- Python 3.12+
- ultralytics
- Pillow
- OpenCV solamente si aporta una ventaja clara
- argparse o Typer para CLI
- pytest

Evitar dependencias innecesarias.

## Arquitectura deseada

Mantener responsabilidades separadas aproximadamente así:

```text
autocrop-ai/
├── app/
│   ├── cli.py                      # creado en etapa 03
│   ├── detector.py
│   ├── subject.py
│   ├── crop.py
│   ├── processor.py                # creado en etapa 03
│   └── models.py       # previsto, no creado aún (solo cuando existan tipos compartidos que lo justifiquen)
├── plans/              # Por etapa: plans/NN-nombre/{plan.md, registro.md}
├── AGENTS.md           # Dinámica Astra/Big Pickle y reglas comunes
├── tests/
├── samples/                        # previsto, no creado aún
├── output/                         # previsto, no creado aún
├── pyproject.toml
└── README.md
```

Nota: en la raíz existen además `fotos/` y `yolo11n.pt` (locales, git-ignorados, solo para validación); no forman parte del producto.

La estructura puede ajustarse si existe una razón técnica clara.

## Reglas de detección

Para el MVP:

- detectar únicamente clase `person`;
- si hay una sola persona, usarla;
- si hay varias, elegir inicialmente la persona con mayor área de bounding box;
- diseñar esa lógica de selección para poder reemplazarla posteriormente por estrategias mejores.

No mezclar la detección YOLO con la lógica de selección del sujeto.

Quiero poder implementar más adelante estrategias como:

- persona más cercana al centro;
- combinación tamaño + centro;
- tracking entre imágenes consecutivas;
- detección de rostro;
- bib number detection;
- selección manual asistida.

## Algoritmo de crop

Implementar una función independiente similar a:

```python
calculate_crop(
    image_width,
    image_height,
    subject_bbox,
    aspect_ratio,
    margin,
)
```

Debe devolver coordenadas enteras (extremos derecho e inferior exclusivos), o `None` si no puede incluir al sujeto completo respetando proporción y límites:

```python
(left, top, right, bottom)
```

El algoritmo debe:

- incluir completamente al sujeto cuando sea posible;
- respetar la relación de aspecto solicitada;
- agregar margen alrededor del bounding box;
- intentar mantener el centro del sujeto cerca del centro del crop;
- desplazar el crop cuando llegue a los bordes;
- nunca producir coordenadas fuera de la imagen;
- evitar deformar la imagen.

Aspect ratios iniciales:

- 1:1
- 4:5
- 3:2
- 2:3
- 16:9


## Decisiones acordadas de encuadre

- Por defecto, conservar la orientación: 3:2 en horizontales y 2:3 en verticales; para imágenes cuadradas, usar 1:1. Resolver orientación EXIF antes de detectar y calcular coordenadas.
- Una proporción indicada explícitamente se aplica a todo el lote, sin invertirla según orientación. El ejemplo `--ratio 3:2` solicita siempre horizontal.
- Margen inicial de 0.15: 15 % del ancho de la caja a cada lado y 15 % del alto arriba y abajo. Ampliar lo necesario para cumplir la proporción.
- Desplazar el recorte en los bordes y reducir el margen si es necesario, siempre incluyendo al sujeto completo.
- Si no existe un recorte válido, o no se detectan personas, copiar el original a `output/review/` y registrar el motivo. Nunca cortar parcialmente al sujeto como fallback ni modificar el original.
- La matemática usa pares enteros de proporción y tamaños enteros con proporción exacta. El contrato detallado está en [la etapa 01](plans/01-crop/plan.md).

## CLI esperada

Algo similar a:

```bash
python -m app.cli \
    --input ./samples \
    --output ./output \
    --ratio 3:2 \
    --margin 0.15
```

Salida esperada:

```text
Processing IMG_001.jpg
Detected 1 person
Selected subject bbox: (...)
Crop: (...)
Saved output/IMG_001.jpg
```

Si no encuentra ninguna persona:

- no fallar;
- registrar el caso;
- copiar el archivo original sin modificar a `output/review/`.

Usar la misma carpeta cuando el recorte solicitado no pueda incluir al sujeto completo, registrando el motivo.

## Testing

Quiero tests especialmente sobre la matemática del crop.

Cubrir como mínimo:

- sujeto centrado;
- sujeto cerca del borde izquierdo;
- sujeto cerca del borde derecho;
- sujeto cerca del borde superior;
- sujeto cerca del borde inferior;
- sujeto grande;
- sujeto pequeño;
- imágenes verticales;
- imágenes horizontales;
- distintos aspect ratios.

La función de crop debería poder probarse sin cargar YOLO.

## Diseño

Priorizar:

- código legible;
- funciones pequeñas;
- type hints;
- separación de responsabilidades;
- comportamiento determinista;
- logs útiles;
- evitar sobrearquitectura.

No crear microservicios, APIs web, bases de datos ni Docker salvo que exista una necesidad real.

## Próximas etapas

NO implementarlas todavía, pero tenerlas presentes para no bloquear la arquitectura:

### Fase 2
Evaluación de foco/nitidez del sujeto.

### Fase 3
Generación de metadata/XMP para Lightroom en lugar de generar JPEG recortado.

### Fase 4
Soporte RAW (`CR3`, `NEF`, `ARW`, etc.).

### Fase 5
Aplicación desktop para Windows.

### Fase 6
Procesamiento eficiente de 5.000–10.000 fotografías.

## Forma de trabajo

La dinámica completa está en [AGENTS.md](AGENTS.md): Astra con razonamiento high define la etapa y sus criterios técnicos y funcionales; Muse escribe primero la suite unitaria, comprueba que falla por comportamiento pendiente y después implementa; Astra revisa tests y código, y Muse corrige hasta cerrar la etapa.

Cada etapa se documenta en una carpeta `plans/NN-nombre/` con dos archivos: `plan.md` (contrato y estado) y `registro.md` (evidencia de ejecución y revisión). No duplicar estados aquí. Las fases futuras del producto listadas arriba no son las etapas de implementación del MVP.

### Etapas del MVP

1. [Matemática del recorte](plans/01-crop/plan.md): contrato de tests e implementación por Muse.
2. [Detección y selección del sujeto](plans/02-deteccion/plan.md): contrato de detección YOLO y selección por mayor área.
3. [Procesamiento de imágenes y CLI](plans/03-procesamiento/plan.md): contrato de procesador con EXIF y CLI por carpeta.
4. [Evaluación del pipeline con fotos reales](plans/04-evaluacion/plan.md): evidencia sobre 13 fotos y veredicto de cierre del MVP.


No escribas todo el proyecto de una sola vez.

Primero:

1. analizá el problema;
2. proponé la arquitectura mínima;
3. explicá las decisiones importantes;
4. creá el proyecto base;
5. escribí y ejecutá primero los tests unitarios de `calculate_crop()`, confirmando fallos por funcionalidad pendiente;
6. implementá `calculate_crop()` hasta cumplir el contrato y pasar los tests;
7. después integrá YOLO;
8. finalmente construí la CLI.

Después de cada etapa, ejecutá los tests y verificá que funcione antes de continuar.

Cuando exista una decisión con trade-offs, explicá brevemente por qué elegiste una alternativa.

El objetivo de esta primera iteración es conseguir un pipeline real funcionando:

```text
JPEG
  ↓
YOLO
  ↓
persona principal
  ↓
bounding box
  ↓
crop automático
  ↓
JPEG de salida
```

No intentes resolver todavía Lightroom ni el filtrado de foco.
