# Traspaso al implementador

El director prepara un encargo que identifica la versión, etapa, contrato, alcance, archivos relevantes y comprobaciones exigidas. El mensaje debe indicar que `AGENTS.md` y el plan de etapa son fuente de verdad y que el implementador solo modifica la etapa asignada. Registrar en `registro.md` el implementador, modelo, comando o sesión y resultados reales; no copiar razonamientos privados ni credenciales.

## OpenCode Muse, predeterminado

Verificar `opencode run --help` y la disponibilidad del modelo en el entorno. Invocar `opencode run` desde la raíz con `--model opencode/muse-spark-1.3-contributor-free`, título de etapa y el encargo. Usar `--session` o `--continue` al devolver hallazgos al mismo implementador. No usar `--auto` por defecto. Si el modelo no está disponible o el comando falla, registrar el bloqueo y consultar al usuario antes de sustituir el implementador.

## Codex u otro implementador indicado por el usuario

Verificar la CLI y el nombre del modelo en el entorno. `codex exec` acepta `-m`, `-C`, `-s` y un prompt por stdin; seleccionar `workspace-write` y conservar la revisión de permisos. No usar opciones que eviten el sandbox o las aprobaciones. Para Claude u otra herramienta, adaptar solo el comando de invocación; el contrato y la evidencia no cambian.

## Entrega

Esperar la terminación del proceso externo y revisar su código de salida, diff y registro. Si el agente deja trabajo parcial, marcarlo como tal. El director ejecuta las comprobaciones pertinentes de manera independiente y registra su propia revisión. Reenviar hallazgos concretos al mismo implementador; no iniciar otra etapa durante la iteración.
