# Etapa 08 — Publicación en Docker Hub

Estado: en revisión

Dependencias: etapa 06 completada; etapa 07 conserva su validación pendiente en Apple Silicon.

## Objetivo y alcance

Preparar la imagen autocrop para distribución desde Docker Hub, con dependencias directas fijadas, soporte amd64/arm64 y un Compose que consuma una imagen publicada. No publicar ni hacer push desde esta etapa.

## Contrato

- Mantener `compose.yaml` para builds locales y añadir `compose.hub.yaml` como override sin builds; `AUTOCROP_IMAGE` identifica la imagen completa y es obligatorio.
- Fijar las dependencias Python directas a versiones verificadas en la imagen actual, y RustFS a un tag de release.
- Documentar tags `0.1.0` y `latest`, buildx para `linux/amd64,linux/arm64` y uso del override.
- Mantener PyTorch CPU instalado exclusivamente desde su índice CPU.
- La optimización OpenCV headless se aplica solo si conserva `pip check` y el contrato de dependencias.

## Criterios

- **F1:** Compose Hub asigna la imagen configurable a cada servicio Autocrop y no contiene builds.
- **F2:** Dockerfile fija las dependencias directas y mantiene PyTorch CPU.
- **F3:** RustFS usa un tag fijo.
- **F4:** README incluye comandos reproducibles de publicación multiarch y consumo.
- **T1:** pruebas automatizadas cubren el override y las fijaciones relevantes.
- **T2:** build e import smoke, `pip check` y validación Compose se ejecutan cuando el entorno lo permita; registrar bloqueos reales.

## Validación

Ejecutar pruebas focalizadas y suite existente, `docker compose config`, build para amd64/arm64 cuando buildx y red estén disponibles, import smoke (`app`, `torch`, `cv2`) y `pip check`. No publicar la imagen ni cerrar la etapa con comprobaciones pendientes.
