# Etapa V2-11 — Registro

## Implementación

- Archivos: `compose.yaml` (imagen de `api`/`worker`/`frontend` a
  `${AUTOCROP_IMAGE:-mondin0/autocrop:latest}`, `build` y servicio V1 intactos),
  `.env` y `.env.example` (`AUTOCROP_IMAGE=mondin0/autocrop:latest`),
  `README.md` (sección «Usar la imagen publicada» con `docker compose up -d
  --pull always` y `docker compose up -d --build`, sin overlay ni push),
  `compose.hub.yaml` eliminado (`git rm`), `tests/test_docker_hub.py`
  (reescrito al contrato V2-11) y `tests/test_v209_consistent.py` (bloque Hub
  actualizado a comandos publicados sin overlay; resto de comprobaciones intacto).
- Rojo previo: `tests/test_docker_hub.py::test_v2_services_use_published_image_default`
  falló con `assert 'autocrop:latest' == '${AUTOCROP_IMAGE:-mondin0/autocrop:latest}'`
  (api) antes de implementar.
- Comandos y resultados reales:
  - Etapa: 33 passed (test_docker_hub + test_compose + 3 tests V2-09 de README/página/wrapper).
  - Suite completa desde `.venv`: 551 passed, 1 skipped
    (`tests/test_archive.py:203`, preexistente: arcname vacío no almacenable con zipfile).
  - `git diff --check`: exit 0.
  - `docker compose --profile v1 config` (con `.env`): `api`/`worker`/`frontend`
    resuelven `mondin0/autocrop:latest`, `autocrop` conserva `autocrop:latest`;
    con `AUTOCROP_IMAGE=example/autocrop:override-1` el override se propaga a
    los tres servicios V2 (sin red ni pull/push).
- Criterios cubiertos: F1 (imagen por `AUTOCROP_IMAGE` con default latest en los
  tres servicios V2; V1/Redis/RustFS intactos), F2 (dos comandos exactos desde la
  raíz, sin overlay), F3 (overlay eliminado de producto y docs; V1 con perfil y
  build), T1 (tests YAML/README/config sin red ni Hub; protecciones V1 y
  verificaciones V2-09 conservadas), T2 (config resuelve con `.env`; sin cambios
  en `.plans/v1/**`, sin archivos nuevos de producto/operación, V2-10 intacta),
  T3 (suite completa, diff-check, sin build/push ni tags/releases creados;
  tag `v1` listado es preexistente).
- Pendientes para el director: revisión del diff y cierre. La decisión compartida
  y la entrada del índice en `.plans/v2/PLAN.md` son del contrato del director
  (preexistentes a esta implementación, no modificadas aquí).


## Revisión

Revisión independiente del director: **aprobada**, sin hallazgos. Se inspeccionó el diff completo (incluidos cambios staged): solo los archivos previstos por el contrato y estos dos documentos de etapa; el servicio V1 conserva imagen/build/perfil; no hay cambios bajo `.plans/v1/**` ni en V2-10; `compose.hub.yaml` fue eliminado y README no conserva referencias al overlay. `.env` y `.env.example` declaran `mondin0/autocrop:latest`.

Comprobaciones independientes:

- `.venv/bin/python -m pytest` → **551 passed, 1 skipped, 1 warning** en 48.71 s. El skip preexistente es `tests/test_archive.py:203`; el warning deprecado de Starlette/httpx ya existía.
- `docker compose --profile v1 config` → exit 0; `api`, `worker` y `frontend` resuelven `mondin0/autocrop:latest`; `autocrop` conserva `autocrop:latest` y perfil V1. La prueba de Compose con override confirma la propagación a los tres servicios V2.
- `git diff HEAD --check` → exit 0, incluyendo la eliminación staged del overlay.
- Revisión de estado/diff y referencias → sin cambios en `.plans/v1/**` o `.plans/v2/10-validacion-cierre`; sin mención operativa del overlay en README. El coordinador confirmó que no ejecutó publicación ni creó tags/releases.

Matriz final: F1, F2, F3, T1, T2 y T3 verificados. V2-10 permanece **en revisión** por F2 y su contrato/evidencia no cambiaron.

Balance: 1 entrega de implementación, 0 hallazgos corregidos y 4 comprobaciones independientes del director (suite, Compose, diff-check y revisión de diff/estados/documentación). Confianza estimada del director: **97 % en la primera entrega** y **97 % en la etapa final**; limita una cifra mayor que no se consultó Docker Hub para comprobar el estado remoto de `latest`, una operación fuera de estas validaciones.
