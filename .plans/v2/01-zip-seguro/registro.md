# Etapa V2-01 — Registro

## Implementación

Implementador: OpenCode Muse (esta sesión).

Archivos modificados:
- `app/archive.py` (nuevo): `process_archive()` + constantes `MAX_INPUT_BYTES` (500 MiB), `MAX_TOTAL_UNCOMPRESSED` (2 GiB), `MAX_ENTRIES` (10.000). Solo biblioteca estándar + `app.processor.process_folder`. Sin `extractall()`; temporales aislados; salida temporal + `os.replace` atómico.
- `tests/test_archive.py` (nuevo): 24 tests públicos F1–F4 (JPEG válido, no-JPEG omitido, revisión, duplicados, rutas peligrosas, enlace, ZIP corrupto, límites comprimido/descomprimido/entradas, fallo del detector, CRC ilegible, firma del contrato, solo-stdlib).
- `.plans/v2/01-zip-seguro/plan.md`: estado `en implementación` → `en revisión` al entregar.
- No se tocó V1 (`app/processor.py`, `app/cli.py`, motor, tests existentes) ni etapas posteriores.

Comandos y resultados reales (desde `.venv`):
- Tests primero contra stub `NotImplementedError`: `.venv/bin/python -m pytest tests/test_archive.py` → 21 failed, 2 passed, 1 skipped. Fallos funcionales (no solo imports): paridad F1/F2 y todos los rechazos F3/F4 vía `check_rejected()` que no acepta `NotImplementedError`; pasan solo firma del contrato y chequeo stdlib. (1 skip: arcname vacío no almacenable con `zipfile`.)
- Tras implementar: `.venv/bin/python -m pytest tests/test_archive.py` → 22 passed, 1 skipped.
- Suite completa: `.venv/bin/python -m pytest` → 372 passed, 1 skipped.
- `.venv/bin/pip check` → `No broken requirements found.`
- Integración YOLO real + JPEG sintético (sin tocar `fotos/`, en `/tmp`): `YOLODetector(yolo11n.pt, 0.25)` sobre ZIP con `synth.jpg` 800x600 → `summary: {'processed': 1, 'saved': 0, 'review': 1, 'skipped': 0}`, `names: ['review.log', 'review/', 'review/synth.jpg']`. Sin bloqueo de entorno.

Corrección de tests durante la implementación (para revisión del director):
- `..` sin sufijo JPEG se eliminó de la parametrización peligrosa: sin `/` ni `\` y sin sufijo `.jpg`/`.jpeg` es no-JPEG y el contrato manda ignorarlo, no rechazarlo.
- `test_rejects_encrypted_entry`: `zipfile.writestr` borra el bit de cifrado; el test ahora lo fija parcheando los headers raw (local + central) y aserta que el bit sobrevive antes de llamar.
- `test_unreadable_member_rejected`: `writestr` recalcula CRC, así que el CRC falso original nunca sobrevivía; el test ahora escribe en `ZIP_STORED` y voltea un byte del payload para forzar error real de CRC en lectura.

Criterios cubiertos: F1 (paridad resumen + bytes contra `process_folder`), F2 (recortes + `review/` + `review.log`, entradas ordenadas, input intacto), F3 (corrupto, sin-JPEG, anidado, peligroso, duplicado case-insensitive, symlink, cifrado, salida existente, 3 límites, sin parcial), F4 (revisión preservada, `RuntimeError` del detector con mensaje exacto sin parcial, ilegible sin parcial, temporales limpiados por `TemporaryDirectory` + `mkstemp`/`os.replace`), T1 (separación del motor, stdlib, test de imports prohibidos), T2 (evidencia roja funcional + suite + `pip check` verdes).

Pendientes para el director: revisión del diff, aserciones y evidencia; cierre de la etapa. No se declara completada.

## Corrección de hallazgos (segunda vuelta)

Evidencia roja funcional antes de modificar producción (código sin corregir):
- Sonda H1 (carrera en publicación): ZIP válido + `process_folder` envuelto que planta `b"rival-bytes"` en `output_zip` a mitad de vuelo → `process_archive` devolvió resumen con éxito y `output bytes rival intact: False`. El `os.replace` sobrescribía al rival sin error.
- Sonda H2 (helper débil): ZIP válido + detector que lanza `RuntimeError("model exploded")` → el `check_rejected()` anterior lo aceptó en silencio como "rechazo". Demuestra que aceptaba fallos de procesamiento como rechazos de entrada.
- Nuevos tests estrictos contra producción sin corregir: `.venv/bin/python -m pytest tests/test_archive.py` → 1 failed, 22 passed, 1 skipped. Solo falla `test_concurrent_output_creation_never_overwrites` (no se lanza `FileExistsError`, el rival se pierde); los rechazos estrictos ya pasan porque la validación corría antes del procesamiento.

Cambios mínimos:
- `tests/test_archive.py`: `Stub` ahora registra `calls`; `Boom` (siempre falla) prueba que la validación precede al procesamiento; `check_rejected()` exige tipo + mensaje pertinentes y `calls == []`. Peligrosos/anidados/duplicados/symlink/cifrado usan `Boom` y esperan `ValueError` de validación (un intento de procesar daría `RuntimeError`); corrupto/sin-JPEG/límites/ilegible/salida-existente usan `Stub` con mensajes (`invalid zip`, `no JPEG`, `2 GiB`, `500 MiB`, `too many entries`, `cannot read entry`, `already exists`). Nuevo `test_concurrent_output_creation_never_overwrites` (rival plantado vía `process_folder` envuelto; exige `FileExistsError` y bytes del rival intactos).
- `app/archive.py`: publicación exclusiva — `os.link(tmp, output_zip)` en lugar de `os.replace`, con `FileExistsError("output already exists: ...")` si el destino aparece a mitad de vuelo; `os.unlink` del temporal tras enlazar. Sin otros cambios.

Comandos y resultados reales (desde `.venv`, tras corregir):
- `.venv/bin/python -m pytest tests/test_archive.py` → 23 passed, 1 skipped.
- `.venv/bin/python -m pytest` (suite completa) → 373 passed, 1 skipped.
- `.venv/bin/pip check` → `No broken requirements found.`
- Integración YOLO real + JPEG sintético en `/tmp` (sin tocar `fotos/`): `{'processed': 1, 'saved': 0, 'review': 1, 'skipped': 0}`, `['review.log', 'review/', 'review/synth.jpg']`. Sin bloqueos.

Criterios: F3 cubre ahora la no-sobrescritura concurrente; F3/F4 con tipos, mensajes y etapa de fallo verificados. V1 intacto (`git status` solo muestra la etapa V2-01). Se devuelve a `en revisión`; no se declara completada.

## Revisión

Primera revisión del director: `.venv/bin/python -m pytest tests/test_archive.py -q` → 22 passed, 1 skipped. Diff y motor `process_folder()` inspeccionados.

- `app/archive.py`, publicación con `os.replace`: si otro proceso crea `output_zip` después de la comprobación inicial, se sobrescribe. Impacto: pérdida de un archivo ajeno; criterio F3 y contrato de salida inexistente. Corrección: agregar primero un test de regresión para la creación concurrente y publicar sin reemplazar una ruta existente.
- `tests/test_archive.py`, `check_rejected()`: acepta cualquier excepción. Impacto: los rechazos F3 pueden pasar por fallos ajenos, incluido un error de procesamiento, sin probar el motivo contratado. Corrección: antes de cambiar producción, exigir tipos y mensajes pertinentes por caso y verificar que los casos peligrosos fallan durante validación.

Segunda revisión del director: inspeccionados el test de carrera, el helper de rechazos y la publicación exclusiva con `os.link`. Ambos hallazgos resueltos: la ruta rival conserva sus bytes y los rechazos exigen tipo y mensaje pertinentes antes de invocar el detector. `.venv/bin/python -m pytest -q` → 373 passed, 1 skipped; `.venv/bin/pip check` → `No broken requirements found.` F1–F4 y T1–T2 verificados. Etapa cerrada.
