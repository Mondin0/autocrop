# Etapa 07 — venv portable en Mac

Estado: en revisión

Dependencias: etapa 06 completada. Implementación: Muse; revisión: agente coordinador.

## Objetivo y alcance

Dejar un `setup-mac.sh` de un comando que prepare en una Mac moderna
(Apple Silicon) un `.venv` funcional con la CLI: crea el entorno, instala
el proyecto con dependencias pinneadas probadas, verifica el hash de
`yolo11n.pt`, corre `--help` y una foto sintética de humo en directorios
temporales (ruta `review`, sin fotos reales y sin tocar `fotos/`).
Pinnear dependencias en `pyproject.toml` y documentar la sección Mac en
README. Excluir cambios en detección/selección/crop, `device="cpu"` y MPS
(futura, no implementada).

## Contrato y decisiones

- Pins en `pyproject.toml`: `ultralytics==8.4.174`, `Pillow==12.3.0`,
  `torch==2.14.1`, `torchvision==0.29.1`, sin sufijo de plataforma para
  que cada OS resuelva su wheel. Si algún pin no tuviera wheel para macOS
  ARM64 en PyPI, elegir el más cercano disponible y documentar el motivo
  en el registro.
- `setup-mac.sh` (nuevo, ejecutable): verifica `python3.12` presente; si
  falta, error claro con cómo instalarlo, sin auto-instalar nada. Crea
  `.venv`, instala el proyecto, verifica el hash sha256 de `yolo11n.pt`
  (`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`;
  falla claro si falta o difiere), corre `--help` y un humo sintético en
  temporales (resumen `1 processed / 1 review`, sin tocar originales).
- Instalación runtime por defecto (`.`, sin extras); `.[dev]` solo con
  `./setup-mac.sh --dev` (criterio simple: flag explícito para quien
  corre tests; documentado en el script y en README).
- No tocar `device="cpu"` ni el pipeline de detección/selección/crop.
  MPS queda como mejora futura registrada, no implementada.
- Bloqueo conocido: en este entorno no hay Mac; la corrida real en Apple
  Silicon queda como comprobación pendiente explícita en el registro
  (comandos Linux sí ejecutados con resultados reales; lo de Mac se
  registra pendiente, no se inventa).

## Criterios de aceptación

- F1: un comando deja venv + `--help` en 0.
- F2: hash de pesos verificado con fallo claro.
- F3: humo sintético `1 processed / 1 review` sin tocar originales.
- F4: sin Python 3.12 el error indica cómo instalarlo.
- T1: suite completa `.venv/bin/python -m pytest` y
  `.venv/bin/python -m pip check` verdes.
- T2: `bash -n setup-mac.sh` limpio.
- T3: sin cambios en `app/` salvo defecto demostrado y aprobado.

## Validación y entrega

Muse escribe primero `tests/test_setup_mac.py` y registra fallos
funcionales reales (pins ausentes, script inexistente), luego implementa.
Ejecuta la suite del archivo, la suite completa, `pip check` y `bash -n`.
En Linux verifica el script donde sea portable (sintaxis, pins, hash,
`--help`, humo sintético con el `.venv` local queda pendiente de Mac si
el entorno no lo permite sin contaminar el repo; usar temporales, nunca
`fotos/`). Registra comandos, resultados reales y bloqueos en
registro.md. Marca `en revisión`; no declara la etapa completada ni
implementa la siguiente.

Revisor inspecciona diff completo, contrato/tests/documentación y ejecuta
comprobaciones apropiadas. Hallazgos con ubicación, impacto, criterio y
corrección esperada. Solo cierra `completada` sin pendientes.
