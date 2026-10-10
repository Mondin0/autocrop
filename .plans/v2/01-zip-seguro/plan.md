# Etapa V2-01 — ZIP seguro alrededor del motor

Estado: completada

Contrato aprobado por el usuario; implementación delegada a OpenCode Muse mediante un subagente coordinador y revisada por el director.

Dependencias: V1 disponible; decisiones compartidas en [V2](../PLAN.md). Implementación por defecto: OpenCode Muse. Revisión: el director que definió esta etapa.

## Objetivo, alcance y exclusiones

Procesar un ZIP local de JPEG a otro ZIP que reproduzca el contenido de la carpeta de salida de `process_folder()`. Agregar una interfaz Python pequeña y probarla sin servicios externos. Esta etapa no incluye API, navegador, Redis, RustFS, progreso en vivo ni cambios de selección, detección o matemática del recorte.

## Contrato y decisiones

- Añadir `process_archive(input_zip: Path, output_zip: Path, detector: object, ratio: tuple[int, int] | None = None, margin: float = 0.15) -> dict[str, int]` en `app/archive.py`. Devuelve el resumen de `process_folder()`; no cambia la firma ni la salida de la CLI V1.
- Validar antes de extraer: archivo ZIP válido de hasta 500 MiB, al menos un JPEG en la raíz, máximo 10.000 entradas y suma declarada de tamaños descomprimidos de hasta 2 GiB. Durante la copia, contar bytes reales y detenerse si superan 2 GiB. Los JPEG anidados hacen fallar el lote; otros archivos no JPEG se ignoran y no entran en el resumen.
- No confiar en rutas del archivo: aceptar solo nombres de JPEG que sean un nombre de archivo simple, sin rutas absolutas, separadores `/` o `\\`, componentes `..`, enlaces simbólicos ni nombres duplicados sin distinguir mayúsculas. No usar `extractall()`. Rechazar entradas cifradas o que no puedan leerse completas. Usar directorios temporales aislados.
- Exigir una ruta de salida inexistente; así tampoco puede identificar el ZIP de entrada por symlink o hard link. No tocar el ZIP original. Crear el ZIP de salida de forma temporal y publicarlo solo al completar el procesamiento; ante fallo no dejar un resultado parcial en la ruta final.
- Ejecutar `process_folder()` sobre los JPEG extraídos y añadir al ZIP final cada archivo producido en la salida, incluidos los recortes de la raíz, una entrada `review/` aunque esté vacía y `review.log`. Conservar nombres y bytes de los archivos de revisión. Ordenar las entradas para que el empaquetado sea determinista.
- Errores de entrada, límites y ZIP inválido deben producir una excepción legible; errores de inferencia siguen el comportamiento actual de `process_folder()` y no se registran como éxito. Limpiar los temporales en ambos casos.

## Criterios

- **F1:** un ZIP válido con JPEG de raíz produce el mismo resumen y los mismos archivos que `process_folder()` sobre esas fotos.
- **F2:** el ZIP final incluye recortes, `review/` y `review.log`; los originales y el ZIP de entrada conservan sus bytes.
- **F3:** ZIP inválidos, vacíos de JPEG, anidados, peligrosos, duplicados o superiores a los límites se rechazan sin salida parcial.
- **F4:** ante foto para revisión o fallo de procesamiento, se preservan respectivamente la salida de revisión o el error, y se limpian temporales.
- **T1:** la lógica ZIP se separa del motor, usa biblioteca estándar y no agrega dependencias de web o almacenamiento.
- **T2:** tests primero con fallo funcional observado; suite completa y `pip check` verdes desde `.venv`.

## Pruebas y validación

Muse crea tests públicos para F1–F4 con detector controlado y temporales: JPEG válido, no JPEG omitido, revisión, nombres duplicados, rutas peligrosas, enlace, ZIP corrupto, límites comprimido/descomprimido y fallo del detector. Comprueba bytes del original, ausencia de salida parcial y limpieza. Ejecuta primero los tests contra una función vacía para demostrar fallos funcionales, después la suite de etapa, suite completa y `pip check`. Una prueba de integración con YOLO real y JPEG sintético confirma el flujo sin tocar `fotos/`. Registra comandos y resultados en [registro.md](registro.md); el director revisa diff, aserciones y evidencia antes de cerrar.
