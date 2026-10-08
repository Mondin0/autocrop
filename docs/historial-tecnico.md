# Historial técnico del MVP

Este documento resume el trabajo realizado desde el inicio hasta la
dockerización. Los contratos, hallazgos y resultados completos de cada etapa
permanecen en `plans/NN-nombre/{plan.md,registro.md}`. El [README](../README.md)
contiene los comandos de uso; [PLAN.md](../PLAN.md) contiene el alcance del
producto y las decisiones compartidas.

## Producto y arquitectura actual

La CLI recibe una carpeta de JPEG, detecta personas con YOLO11n, elige la caja
de mayor área y calcula un recorte con proporción y margen configurables.
`app/detector.py` adapta Ultralytics; `app/subject.py` selecciona el sujeto;
`app/crop.py` calcula coordenadas sin leer imágenes; `app/processor.py` lee,
orienta según EXIF, guarda recortes y envía a `review/` los casos sin persona,
sin recorte válido o ilegibles; `app/cli.py` ofrece los argumentos y el resumen
del lote. Docker empaqueta esta misma CLI en CPU, con los pesos locales dentro
de la imagen y carpetas de entrada/salida montadas desde el host.

El formato inicial es JPEG y la lectura de entrada no es recursiva. La
orientación determina la proporción por defecto: 3:2 horizontal, 2:3 vertical,
1:1 cuadrada. Una proporción explícita rige todo el lote. El margen por defecto
es 0.15. El original debe conservarse; los casos enviados a `review/` se copian
sin alteraciones y se registran en `review.log`.

## Etapas realizadas

| Etapa | Entrega y verificación | Decisión o límite vigente |
| --- | --- | --- |
| [01 — Matemática](../plans/01-crop/plan.md) | `calculate_crop()` devuelve coordenadas enteras, dentro de la imagen, con proporción exacta, o `None` cuando no cabe el sujeto. Pruebas de bordes, proporciones, entradas inválidas y un oráculo independiente de geometría. | La geometría es pura y se puede probar sin YOLO ni fotos. |
| [02 — Detección y selección](../plans/02-deteccion/plan.md) | Adaptador YOLO para clase `person` y selección determinista de la caja de mayor área; pruebas con backend simulado y prueba real en CPU. | La caja más grande no siempre es el sujeto que quería el fotógrafo. |
| [03 — Procesamiento y CLI](../plans/03-procesamiento/plan.md) | Lectura JPEG, orientación EXIF, procesamiento por carpeta, salida de recortes, `review/` y `review.log`; prueba real con pesos locales. La suite llegó a 301 tests. | Una excepción de inferencia puede interrumpir el lote. |
| [04 — Evaluación con fotos](../plans/04-evaluacion/plan.md) | Dos corridas sobre 13 fotos, inspección visual por foto, hashes de originales y resultados repetidos. Detección: 13/13; selección y composición: 10/13. | El MVP es parcialmente usable: hubo un microrecorte sin sujeto principal y dos elecciones/composiciones incorrectas. |
| [05 — Seguridad de rutas](../plans/05-seguridad-rutas/plan.md) | Rechazo previo de carpetas equivalentes y destinos que identifican originales, incluso por symlink o hard link; CLI informa el conflicto antes de construir el detector. Suite: 318 tests. | Se permiten carpetas padre/hija cuando no hay colisión con un original. |
| [06 — Docker](../plans/06-dockerizacion/plan.md) | Imagen CPU con YOLO11n local, comando `autocrop`, Compose con contenedor persistente, `/input` solo lectura y `/output` escribible. Se verificaron inferencia sin red, permisos, hashes, errores y 323 tests. | La imagen pesa aproximadamente 2.46 GB; las versiones de base y paquetes no están fijadas para reconstrucciones futuras. |

Cada etapa siguió el ciclo del [AGENTS.md](../AGENTS.md): contrato, tests
primero, implementación y revisión con hallazgos en su `registro.md`. Las
cuentas de tests corresponden al cierre de cada etapa; no son métricas de
calidad fotográfica. Las correcciones y cambios de interpretación conservan su
evidencia en los registros originales.

## Resultado de la evaluación fotográfica

La [tabla por foto de la etapa 04](../plans/04-evaluacion/registro.md) muestra
13 salidas `saved` y ninguna enviada a `review/`. En `Empty_road_mongolia.jpg`
se guardó un recorte de 123×82 píxeles pese a no haber sujeto principal claro.
En la foto grupal de Viena se eligió un corredor de espaldas; en
`DSC09438.jpg.jpeg` se eligió un corredor lateral en lugar del central. La
inspección concluyó que la detección encontró personas plausibles en las 13
fotos, mientras que selección y composición resultaron útiles en 10.

La etapa 05 resolvió el riesgo de sobrescribir originales por rutas de salida.
Quedan como trabajo futuro la decisión sobre tamaño mínimo de recorte, una
mejor estrategia de selección y la política ante fallos de inferencia dentro
de un lote. La dockerización no cambia estos resultados del procesador.

## Estado de Docker y dependencias

La [guía Docker](../README.md#docker) explica el uso y la consulta de versiones
de la imagen existente. La imagen comprobada el 2026-10-08 usa Python 3.12.15,
PyTorch 2.14.1+cpu, torchvision 0.29.1+cpu, Ultralytics 8.4.174 y Pillow
12.3.0; `pip check` pasó dentro de ella. Son versiones observadas. El
Dockerfile emplea una etiqueta móvil de Python y resoluciones sin versiones
exactas para los paquetes, de modo que un nuevo build puede producir otra
combinación. Los pesos `yolo11n.pt` se toman del archivo local presente al
construir la imagen; no se descargan durante la ejecución.
