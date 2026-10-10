# Etapa V2-02 — Registro

## Implementación

Implementador: OpenCode Muse (esta sesión).

Archivos modificados:
- `app/processor.py`: `process_folder()` suma parámetro opcional final `on_progress=None` (compatible con llamadas V1 de 5 args). Emite dict nuevo antes/después de cada JPEG con exactamente `current/procesado/total/saved/review`; `total=len(batch)`; sin eventos para omitidos; ante excepción no hay evento posterior y el error se propaga. Sin duplicar el motor: una sola pasada por `_execute`.
- `app/archive.py`: `process_archive()` suma parámetro opcional final `on_progress=None`. Tras extracción completa emite inicial (`current=None`, ceros); delega los 2n intermedios a `process_folder()` pasándole el callback (una sola pasada, sin reprocesar); tras publicar el ZIP con `os.link` emite final (`current=None`, `processed=total`) y devuelve el resumen. Fallo de detector/escritura/callback propaga sin evento final ni parcial; fallo del callback final propaga con el ZIP completo ya publicado. `total` renombrado a `written` para el contador de bytes (sin cambio de comportamiento).
- `tests/test_progress.py` (nuevo): 10 tests F1–F4/T1 con JPEG sintéticos y detector controlado (secuencia 2n+2 con orden y contadores, dicts independientes, paridad con/sin callback, firmas compatibles, un solo `process_folder` + N llamadas al detector, ZIP inválido/ilegible sin eventos, fallo de detector/callback sin parcial, final tras publicar + ZIP completo ante fallo del callback final, solo-stdlib).
- `tests/test_archive.py`: `test_signature_matches_contract` acepta el 6.º parámetro opcional `on_progress=None` (ver motivo abajo). Sin otros cambios.
- `.plans/v2/02-avance-por-foto/plan.md`: estado `en implementación` → `en revisión` al entregar.

Comandos y resultados reales (desde `.venv`):
- Tests primero contra implementación ausente: `.venv/bin/python -m pytest tests/test_progress.py -q` → 9 failed, 1 passed. Fallos funcionales (no de importación): `TypeError` por `on_progress` inexistente + aserción de firma; los tests importan y el motor llega a procesar (`Processing a.jpg` en stdout). Solo pasa el chequeo stdlib.
- Tests contra stub mínimo (`on_progress` aceptado pero `NotImplementedError` si no es `None`): misma suite → 8 failed, 2 passed, todos `NotImplementedError` salvo firma y stdlib. Evidencia roja funcional.
- Tras implementar: `.venv/bin/python -m pytest tests/test_progress.py` → 10 passed in 0.15s.
- Suite completa: `.venv/bin/python -m pytest` → 383 passed, 1 skipped in 8.71s.
- `.venv/bin/pip check` → `No broken requirements found.`

Corrección de test durante la implementación (para revisión del director):
- `tests/test_archive.py::test_signature_matches_contract` exigía exactamente 5 parámetros V2-01. El contrato V2-02 aprobado exige `on_progress` opcional final en `process_archive()` conservando las llamadas existentes; el test ahora exige los 5 primeros iguales y, si hay 6.º, que sea `on_progress=None`. Sin este ajuste la suite completa no puede pasar con el contrato vigente.

Criterios cubiertos: F1 (secuencia inicial/antes/después/final, orden determinista, `processed==saved+review`, dicts nuevos e independientes), F2 (resumen, ZIP e input idénticos con/sin callback; `process_folder` sin callback conserva resumen), F3 (inválido/ilegible sin eventos; fallo de detector/callback conserva emitidos sin parcial), F4 (final aserta `out.exists()` dentro del callback; fallo del final deja ZIP completo igual al de referencia), T1 (reutiliza `process_folder`, una llamada, N detecciones, sin dependencias nuevas), T2 (rojo funcional + etapa + completa + `pip check` verdes).

Pendientes para el director: revisión del diff, aserciones y casos límite; cierre de la etapa. No se declara completada. No se tocó V1 (`app/cli.py`, motor de recorte) ni otras etapas salvo el ajuste de firma citado.

## Iteración H1 (regresión pre-foto, sin cambio en producción)

Alcance: atender únicamente el hallazgo H1 de la Revisión. No se corrige ni amplía ningún otro aspecto.

Regresión agregada en `tests/test_progress.py`:
- `test_f3_callback_failure_on_first_before_photo_no_detect_no_output`: el callback falla en el evento pre-foto de la primera foto (`current == "a.jpg"`, `processed == 0`) y comprueba que `stub.calls == []` (detector nunca invocado) y que no se publicó salida (`not out.exists()`), además de los 2 eventos entregados (inicial + pre-foto) con claves y contadores correctos.

Evidencia (desde `.venv`, sin tocar producción antes del rojo):
- `.venv/bin/python -m pytest tests/test_progress.py::test_f3_callback_failure_on_first_before_photo_no_detect_no_output -q` → 1 passed, exit 0. Resultado verde: el comportamiento actual ya emite el evento pre-foto antes de invocar al detector, por lo que no hubo fallo que corregir y no se modificó producción.
- `.venv/bin/python -m pytest tests/test_progress.py -q` → 11 passed, exit 0.
- `.venv/bin/python -m pytest` (suite completa) → 384 passed, 1 skipped, exit 0.
- `.venv/bin/pip check` → `No broken requirements found.`, exit 0.

Producción intacta en esta iteración (`git diff` no muestra cambios en `app/` respecto al estado entregado); el diff de la iteración es solo el test de regresión más este registro. `plan.md` queda en `en revisión`. H1 se conserva en la sección Revisión para que el director lo cierre.

## Revisión

Primera revisión independiente del director:
- `.venv/bin/python -m pytest -q` → 383 passed, 1 skipped.
- `.venv/bin/pip check` → `No broken requirements found.`
- Diff de `app/archive.py`, `app/processor.py` y tests inspeccionado contra F1–F4 y T1–T2. Sin hallazgos en secuencia, nombres, contadores, paridad, no publicación parcial, publicación previa al evento final ni reutilización del motor.
- Hallazgo H1 — `tests/test_progress.py::test_f3_callback_failure_before_final`: el callback falla en el tercer evento, después de terminar la primera foto. El plan exige cubrir fallo del callback antes de procesar; falta demostrar que una excepción en el evento pre-foto detiene el procesamiento de esa foto. Impacto: la ruta de fallo en el callback previo no queda probada (F3 y casos de prueba). Corrección esperada: agregar primero una regresión en la que el callback falle en el evento pre-foto inicial y comprobar que el detector no fue invocado ni se publicó salida.

Segunda revisión independiente del director:
- H1 resuelto: la regresión agregada hace fallar el callback en el evento pre-foto de `a.jpg` y comprueba cero llamadas al detector y ausencia del ZIP de salida. La prueba pasa contra la implementación existente; no hizo falta cambiar producción.
- `.venv/bin/python -m pytest tests/test_progress.py::test_f3_callback_failure_on_first_before_photo_no_detect_no_output -q` → 1 passed.
- Verificación final reportada por Muse: tests de etapa 11 passed; suite completa 384 passed, 1 skipped; `.venv/bin/pip check` sin dependencias rotas.
- Revisión cerrada: F1–F4 y T1–T2 verificados. Dos entregas; un hallazgo corregido mediante test regresivo; la implementación de producción no requirió correcciones. Confianza estimada del director: primera entrega 86% (faltaba el caso de callback pre-foto); entrega final 94% (criterios cubiertos, ejecución independiente de la regresión y suite final reportada; esta etapa no ejercita los servicios web excluidos por contrato).
- Etapa completada.
