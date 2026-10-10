# Etapa 02 — Detección y selección del sujeto

Estado: completada

Dependencias: [etapa 01 completada](../01-crop/plan.md). Implementación: Muse. Revisión: Astra.

## Objetivo

Obtener cajas de personas mediante YOLO y elegir como sujeto la persona con mayor área de caja. Entregar su caja en el mismo sistema de coordenadas que acepta `calculate_crop()`, sin mezclar detección, selección y matemática.

Esta etapa agrega detección real, no todavía el procesamiento de carpetas. Las decisiones generales siguen en [PLAN.md](../PLAN.md); el ciclo de trabajo, en [AGENTS.md](../../../AGENTS.md).

## Alcance y entregables

- `app/detector.py`: adaptador de Ultralytics, carga del modelo y detección sobre una imagen en memoria.
- `app/subject.py`: selección pura por área, independiente de Ultralytics y Pillow.
- `tests/test_detector.py` y `tests/test_subject.py`: tests unitarios previos a la implementación, con backend simulado para detección.
- Actualizar `pyproject.toml` con dependencias de ejecución `ultralytics` y `Pillow`, y `README.md` con instalación, preparación de pesos y uso de las dos piezas.
- Evidencia de prueba real y revisión en [registro.md](registro.md).

No crear `models.py`: una caja como tupla alcanza; no necesitamos clases compartidas, interfaces de estrategias ni un registro de detectores.

## Exclusiones

CLI, recorrer carpetas, abrir/guardar/copiar fotografías en producción, resolver EXIF, elegir proporción automática, recortar píxeles y generar `output/review/` pertenecen a la etapa 03. Tampoco implementar GPU configurable, entrenamiento, tracking, estrategias por centro/confianza, rostros, dorsales, filtros de nitidez ni optimización de lotes.

No cambiar el contrato ni la implementación de `calculate_crop()`. Preservar todos los tests y el historial de la etapa 01.

## Contratos públicos

### Detector

```python
class YOLODetector:
    def __init__(self, weights: pathlib.Path, confidence: float = 0.25) -> None:
        ...

    def detect_people(
        self, image: PIL.Image.Image
    ) -> list[tuple[float, float, float, float]]:
        ...
```

- `weights`: ruta local a un archivo `.pt` existente. No interpretar una ruta inexistente como nombre de modelo descargable. Archivo inexistente: `FileNotFoundError`; directorio: `ValueError`. Otros errores de lectura/carga se propagan.
- Modelo inicial para la validación: **YOLO11n de detección preentrenado en COCO**, `yolo11n.pt`. Se elige una variante pequeña para validar en CPU, no por ser la última disponible. Obtener los pesos explícitamente antes de ejecutar; no descargarlos desde el adaptador ni desde tests.
- Rechazar con `ValueError` modelos cuya tarea no sea detección o cuyo mapa de clases no tenga `0: person`. No soportar por ahora modelos personalizados con otro mapa de clases.
- `confidence`: `int` o `float` finito en `(0, 1]`, nunca booleano. Entradas inválidas: `ValueError`. El umbral es ajustable porque su utilidad depende de las fotos, sin exponer todavía una CLI.
- Cargar YOLO una sola vez por instancia; reutilizar el modelo en llamadas sucesivas. Sin caché global ni carga de pesos al importar módulos.
- `image`: una imagen Pillow RGB, con dimensiones positivas, ya cargada y orientada por el llamador. Rechazar otro tipo, modo o dimensiones con `ValueError` antes de inferir. No abrir rutas, convertir modos ni aplicar EXIF silenciosamente.
- Ejecutar una predicción para esa imagen: `classes=[0]`, `conf=confidence`, `device="cpu"`, `imgsz=640`, `augment=False`, `verbose=False`, `save=False`, `save_txt=False` y `save_crop=False`.
- Extraer `boxes.xyxy`, `boxes.cls` y `boxes.conf` del único resultado. Las coordenadas son píxeles de la imagen original entregada, no coordenadas normalizadas ni del lienzo interno de YOLO. No aplicar otro escalado ni redondear.
- Mantener solamente clase 0 y confianza mayor o igual al umbral, incluso si un backend simulado devuelve otras filas. Mantener el orden relativo del backend.
- Cada caja devuelta es una tupla de cuatro floats finitos `(left, top, right, bottom)`, con `0 <= left < right <= image.width` y `0 <= top < bottom <= image.height`. Los extremos tienen la misma interpretación geométrica que la etapa 01, sin sumar un píxel.
- Una imagen sin detecciones devuelve `[]`. Un resultado sin filas de cajas también es vacío; no confundirlo con falta del resultado de la imagen.
- Una respuesta estructuralmente inválida (cantidad de resultados distinta de uno, filas desalineadas) o una detección de persona retenida con caja/confianza inválida produce `RuntimeError` descriptivo. No clipear ni descartar silenciosamente una caja retenida inválida.
- Los errores de inferencia se propagan; no devolver `[]` cuando el modelo falló. No mutar ni guardar la imagen recibida.

### Selección

```python
def select_subject(
    boxes: collections.abc.Sequence[tuple[float, float, float, float]],
) -> tuple[float, float, float, float] | None:
    ...
```

- Aceptar una secuencia de cajas (por ejemplo lista o tupla), no strings ni generadores. Vacía: `None`; una caja: devolver esa caja.
- Validar todas las cajas antes de seleccionar: tupla de cuatro coordenadas `int` o `float` finitas, sin booleanos, no negativas y con `left < right`, `top < bottom`. Entradas inválidas producen `ValueError`, aunque la caja inválida no hubiese ganado.
- No conoce dimensiones de imagen; el detector garantiza los límites superiores. No convertir obligatoriamente enteros a float al validar o seleccionar: conservar la precisión de entradas enteras.
- Elegir la mayor área `(right-left)*(bottom-top)`. Ante áreas iguales, gana la primera caja de la secuencia. No usar confianza, centro ni orden lexicográfico como desempate.
- Devolver la caja original sin modificar ni reordenar la secuencia. Función pura; el resultado es determinista para la misma entrada y orden.
- La regla aproxima al sujeto principal: una persona de fondo puede ganar si su caja es mayor. No prometer identificación semántica del protagonista ni agregar heurísticas para compensarlo.

## Decisiones de integración y entorno

- Flujo a validar: imagen RGB ya orientada → `detect_people()` → `select_subject()` → `calculate_crop()` con dimensiones de esa misma imagen.
- Etapa 03 asumirá apertura, conversión RGB y orientación EXIF **antes** de detectar. Aquí solo se fija esa precondición; no se implementa el procesador.
- `subject.py` no importa detector, Pillow, Torch ni Ultralytics. Importar `crop.py` o `subject.py` no debe inicializar el backend pesado. Preferir importación de Ultralytics al construir el detector.
- Instalar todo dentro de `.venv`. No agregar OpenCV como dependencia directa: Ultralytics puede traerlo transitivamente, pero la aplicación no lo utiliza en esta etapa.
- Registrar versiones efectivamente utilizadas de Python, Pillow, Ultralytics y Torch, y archivo/hash de pesos en la prueba real. No cambiar modelos o umbral entre casos sin anotarlo.
- Solo usar pesos de una fuente oficial confiable: no cargar archivos `.pt` arbitrarios. Documentar en README el origen y la licencia AGPL-3.0 de Ultralytics/pesos oficiales; revisar condiciones antes de distribuir el producto. No sumar empaquetado comercial en esta etapa.

## Criterios funcionales

- **F1:** detectar exclusivamente personas que alcanzan el umbral, conservando orden y coordenadas originales válidas.
- **F2:** ausencia de personas devuelve `[]` y selección vacía devuelve `None`; errores de carga/inferencia no se presentan como ausencia de personas.
- **F3:** seleccionar una sola caja o la de mayor área entre varias; en empate, la primera. No alterar entradas.
- **F4:** validar rutas, imagen, umbral, cajas y respuesta del backend según los contratos; distinguir entradas inválidas de fallos del backend.
- **F5:** una caja seleccionada se puede pasar directamente a `calculate_crop()`; los resultados geométricos cumplen el contrato de la etapa 01 o devuelven `None` por imposibilidad real.
- **F6:** ejecutar una prueba local con modelo real en CPU y comprobar visualmente que las cajas pertenecen al sistema de coordenadas de la fotografía y que la selección sigue la regla de área.

## Criterios técnicos

- **T1:** separación de detección, selección y geometría; solo dos módulos nuevos de producción, sin abstracciones para estrategias futuras.
- **T2:** tests escritos primero, fase roja por funcionalidad pendiente, fase verde y suite completa registrada; ninguna regresión existente eliminada, debilitada o marcada como esperada.
- **T3:** tests unitarios sin pesos reales, red, GPU ni inferencia real. Simular el límite de Ultralytics, no los resultados de la función de producción que se está probando.
- **T4:** modelo cargado una sola vez por instancia, sin descargas automáticas del adaptador, sin escrituras de predicciones y sin modificar originales.
- **T5:** type hints, docstrings, selección en un recorrido lineal (incluida validación), dependencias y comandos reproducibles en `.venv`. No garantizar identidad bit a bit de inferencia entre versiones/hardware; sí conversión y selección deterministas sobre la misma respuesta.

## Casos de prueba vinculados

### Selección — F2, F3, F4; T1, T2, T3

- Vacía; una caja; varias con ganadora al principio, medio y final.
- Caja ancha frente a caja alta: elegir por área, no por ancho/alto aislados.
- Empate con cajas distintas e inversión del orden: gana siempre la primera.
- Coordenadas fraccionarias, área mínima y enteros mayores que el rango de float; no colapsar extremos distintos ni lanzar `OverflowError` por comprobar finitud de un entero.
- Tipo/longitud incorrectos, booleanos, negativos, NaN/infinito, caja vacía/invertida y caja inválida detrás de una válida. No mutación y llamadas repetidas.

### Detector simulado — F1, F2, F4; T2, T3, T4

- Comprobar argumentos de predicción; dos llamadas reutilizan la misma carga.
- Clase persona y otras clases; confianza inferior, igual y superior al umbral; cajas fraccionarias y junto a los límites de imagen.
- Vacío; cajas devueltas como valores Python sin exponer tensores del backend.
- Imagen no RGB, tipo incorrecto; umbrales inválidos, incluidos booleanos y enteros enormes; ruta ausente/directorio y modelo incompatible.
- Respuesta desalineada, ausencia/multiplicidad de resultados, caja retenida fuera de límites o no finita, confianza retenida inválida. Fallos de carga/inferencia propagados.
- No se llama a YOLO con entradas inválidas; no se modifica la imagen (comparar modo, dimensiones y bytes antes/después con backend simulado).

### Unión sin modelo real — F5; T1–T3

- Backend simulado devuelve en imagen 1000×800 la caja `(400,300,600,500)`: seleccionar y calcular con `1:1`, margen `0.15` → `(370,270,630,530)`.
- Varias personas: la caja ganadora llega intacta al cálculo. Vacío: selección `None`, sin inventar una caja de imagen completa.
- Caja válida alta en imagen 600×1000, `(100,50,500,950)`, proporción `3:2` → `None`; distinguir imposibilidad de recorte de ausencia de personas.

## Procedimiento de implementación y validación

1. **Preparar:** leer contrato/historial y marcar `en implementación`. Comprobar baseline de la suite existente (115 tests al cierre de etapa 01), conservando sus archivos e historial.
2. **Tests primero:** crear tests y estructura mínima/stubs. Ejecutar `.venv/bin/python -m pytest tests/test_subject.py tests/test_detector.py -v`; registrar fallos por comportamiento pendiente, no por importación/instalación.
3. **Implementar:** mínima solución del contrato; registrar correcciones de expectativas solo si estaban equivocadas respecto del plan. Para defectos nuevos, agregar regresión roja antes del fix.
4. **Verificar:** ejecutar tests nuevos, `.venv/bin/python -m pytest` y `.venv/bin/python -m pip check`. Registrar comandos/resultados reales y criterios cubiertos. No incorporar la prueba de inferencia real a la suite unitaria ni introducir skips para reemplazar evidencia faltante.
5. **Prueba real separada:** obtener explícitamente pesos y fotos autorizadas. Usar al menos tres JPEG: una persona principal clara, varias personas y una imagen sin personas. Abrirlas solo para la validación, preparar RGB/orientación y ejecutar el adaptador en CPU con el mismo modelo/umbral. Registrar dimensiones, cajas, selección, tiempo observado, versiones y hash de pesos. Comprobar visualmente límites/escala y mayor área; en el caso sin personas registrar posibles falsos positivos, no ocultarlos. Las anotaciones visuales, si se generan, son archivos nuevos, nunca sobrescriben originales.
6. **Entregar y revisar:** marcar `en revisión`; Astra inspecciona contrato, tests, código, evidencia real y diff completo. No basta la suite verde ni la afirmación del implementador. Cerrar solo con criterios verificados y sin hallazgos pendientes; si faltan fotos/pesos o hay un bloqueo de entorno, registrar lo pendiente y no cerrar.

Las fotos de prueba no fijan una métrica general de precisión deportiva: esa evaluación pertenece a la etapa 04. Un falso positivo aislado no cambia la política de selección ni autoriza nuevas heurísticas; registrar la limitación. Fallos de escala, carga o filtrado sí bloquean esta etapa.

## Referencia técnica

Documentación oficial consultada mediante Context7 para la API Python de Ultralytics: [uso Python](https://docs.ultralytics.com/usage/python/), [predicción](https://docs.ultralytics.com/modes/predict/) y [detección](https://docs.ultralytics.com/tasks/detect/). Confirmar compatibilidad con la versión instalada al implementar; no sustituir el contrato con defaults implícitos de la biblioteca.

No delegar ni implementar por el solo hecho de crear este plan. No iniciar etapa 03 al terminar esta entrega.
