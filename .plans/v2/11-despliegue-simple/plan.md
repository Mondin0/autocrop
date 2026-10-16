# Etapa V2-11 — Despliegue simple

Estado: completada

Dependencias: V2-04 (Compose), V2-09 (documentación coherente). V2-10 continúa en revisión por F2 y no es dependencia de esta etapa.

## Objetivo

Permitir iniciar los servicios V2 con la imagen publicada en Docker Hub usando el Compose principal, sin overlay ni build repetido, y conservar un comando explícito para desarrollo local.

## Alcance y exclusiones

Incluye `compose.yaml`, `.env`, `.env.example`, `README.md`, `compose.hub.yaml` y las pruebas de Compose/Docker Hub/README que describen este flujo. Se actualiza el índice y decisión compartida únicamente en V2.

No incluye publicación/tag/release, `docker build`/`push` ejecutado por el repositorio, modificación de la implementación de servicios, nuevos archivos, variables, servicios ni profiles. No modificar `.plans/v1/**`; no cambiar estado ni evidencia de V1. No reabrir ni cerrar V2-10.

## Contratos y decisiones

- En `api`, `worker` y `frontend`, la referencia de imagen es `${AUTOCROP_IMAGE:-mondin0/autocrop:latest}`. El valor declarado en `.env` y `.env.example` es `mondin0/autocrop:latest`; una definición existente en `.env` selecciona la imagen publicada por defecto en lugar del tag antiguo `0.1.0`.
- El servicio V1 `autocrop` permanece exactamente en `image: autocrop:latest`, con su perfil, comando y build actuales. La configuración publicada es para el stack V2. Para V1 se conserva `docker compose --profile v1 up -d --build`.
- El usuario informa que ya publicó manualmente `mondin0/autocrop:0.2.0`; esta etiqueta es contexto de disponibilidad, no cambia el valor predeterminado solicitado (`mondin0/autocrop:latest`) ni habilita una publicación desde esta etapa.
- Se elimina `compose.hub.yaml`. El Compose principal no requiere `-f` adicionales ni overlay para consumir la imagen; su `build` existente permanece para desarrollo local.
- README documenta, desde la raíz del repositorio, `docker compose up -d --pull always` para la imagen publicada y `docker compose up -d --build` para desarrollo local. La sección Docker Hub ya no requiere export manual de `AUTOCROP_IMAGE`; puede explicar su override mediante `.env` si corresponde. Se quitan instrucciones/referencias residuales al overlay. La publicación de imágenes queda como operación manual externa; esta etapa no afirma ni realiza un push.
- Las pruebas describen los tres servicios V2, el valor por defecto y el fallback/override de Compose cuando sea verificable sin acceder a Docker Hub; conservan la aserción de invariancia V1 y verifican los dos comandos documentados. Los tests README preexistentes de V2-09 mantienen sus demás comprobaciones de perfil V1, recuperación y límites.

## Criterios funcionales

- **F1:** Compose configura `api`, `worker` y `frontend` con la imagen elegida por `AUTOCROP_IMAGE`, cuyo valor predeterminado es `mondin0/autocrop:latest`; Redis/RustFS y el servicio V1 no reciben ese cambio.
- **F2:** el consumidor puede seguir las instrucciones README para usar la imagen publicada con `docker compose up -d --pull always`, sin overlay, y para desarrollo local con `docker compose up -d --build`.
- **F3:** desaparecen `compose.hub.yaml` y sus referencias operativas/documentales; V1 conserva el comando con perfil y build documentado.

## Criterios técnicos

- **T1:** pruebas cubren configuración YAML y README sin depender de red, credenciales Docker Hub o imágenes descargadas; se mantienen las protecciones de la configuración V1 y las verificaciones relevantes de V2-09.
- **T2:** `docker compose config` resuelve la configuración predeterminada con `.env`; el diff no modifica `.plans/v1/**`, no añade archivos de producto/operación fuera de los documentos requeridos de esta etapa ni cambia el estado/evidencia de V2-10.
- **T3:** suite completa, `git diff --check` y revisión del director verifican criterios y ausencia de publicación/tag/release. La etapa no altera el estado de V2-10.

## Casos y validación

1. F1/T1/T2: inspeccionar YAML parseado y ejecutar `docker compose config`; comprobar en la salida que `api`, `worker` y `frontend` usan `mondin0/autocrop:latest`, que `autocrop` conserva `autocrop:latest` y que Redis/RustFS siguen con sus imágenes actuales. En una prueba de configuración con override de entorno, comprobar que `AUTOCROP_IMAGE` se propaga a los tres servicios V2.
2. F2/F3/T1: ejecutar pruebas de `tests/test_docker_hub.py`, `tests/test_compose.py` y `tests/test_v209_consistent.py`; comprobar que README contiene los dos comandos exactos, no referencia el overlay y conserva el arranque V1 con perfil explícito. La lectura del YAML/README y tests no contactan Docker Hub.
3. T1/T3: ejecutar suite completa desde `.venv`, `git diff --check` y revisar el diff completo. Verificar que no existe el overlay, no se modificó `.plans/v1/**`, V2-10 permanece `en revisión` y no se ejecutaron comandos de build/push de publicación ni se crearon tags/releases.

Resultados reales, archivos, comandos y pendientes se registran en [registro.md](registro.md). La validación configura Compose, pero no descarga ni publica la imagen.
