# Etapa 05 — Protección contra sobrescritura de originales

Estado: completada

Dependencias: [etapa 03 completada](../03-procesamiento/plan.md),
[etapa 04 completada](../04-evaluacion/plan.md).
Implementación: Muse. Revisión: Astra.

## Objetivo y alcance

Impedir que el procesador sobrescriba una foto original por una ruta de salida
equivalente. Cambiar `app/processor.py`, `app/cli.py`, sus pruebas y esta
documentación. No reabrir etapas 01–04.

## Contrato

- `process_folder` rechaza con `FileExistsError` si entrada y salida resuelven
  a la misma carpeta, antes de crear salida o procesar archivos. Rutas relativas
  equivalentes y alias por symlink cuentan como iguales.
- Carpetas padre/hija son válidas. El control de archivo impide que el destino
  JPEG o el destino de revisión coincidan con el archivo fuente, también al
  procesar una carpeta.
- `process_image` rechaza antes de crear carpetas o invocar detector cuando
  salida o revisión identifican el original por ruta canónica, symlink o hard
  link preexistente.
- `process_folder` verifica los destinos JPEG, de revisión y del log contra
  todos los originales del lote antes de crear directorios, escribir archivos
  o invocar al detector; ante un conflicto rechaza con `FileExistsError` sin
  crear ni sobrescribir salidas ni log.
- Ante igualdad de carpetas, la CLI informa el conflicto brevemente y retorna
  distinto de cero antes de construir el detector. Los errores públicos
  existentes se conservan.
- Rutas distintas mantienen el procesamiento vigente. No cambiar selección ni
  agregar tamaño mínimo de crop.

## Criterios

- **F1:** carpeta igual, relativa equivalente y alias symlink rechazados sin
  tocar originales, salida, log ni detector.
- **F2:** destino de archivo idéntico, symlink o hard link al original
  rechazado sin alterar el hash del original.
- **F3:** CLI da error legible y no construye detector ante igualdad de carpetas.
- **F4:** combinación válida sigue procesando normalmente.
- **T1:** validación canónica no requiere que salida exista; padre/hija siguen
  permitidas salvo colisión del archivo concreto.
- **T2:** suite completa y `pip check` verdes, sin dependencias nuevas.

## Casos y validación

Pruebas unitarias con temporales y detector stub, primero en rojo por ausencia
de protección. Luego correr `.venv/bin/python -m pytest` y
`.venv/bin/python -m pip check`. No hace falta otra corrida YOLO con fotos
reales.
