# Traspaso al implementador

El director elige un modelo gratuito disponible en OpenCode Zen y apto para la etapa, salvo indicación expresa del usuario. Si duda sobre disponibilidad, coste o aptitud, se detiene y consulta al usuario con AskUserTool o la herramienta equivalente de preguntas; no sustituye Zen por otro proveedor ni elige un modelo de pago por su cuenta. Prepara un encargo breve que identifica versión y etapa y remite a `AGENTS.md` y al contrato aprobado como fuentes de verdad, sin copiar el plan al prompt. Añade solo restricciones operativas necesarias: modificar únicamente la etapa asignada, tests primero con evidencia roja funcional, validaciones exigidas y registro de resultados. Lanza un subagente coordinador que ejecuta la CLI del implementador externo y espera su terminación. Registrar en `registro.md` el modelo elegido, motivo breve, comando o sesión, número de entregas y resultados reales; no copiar razonamientos privados ni credenciales.

## OpenCode Zen

Verificar `opencode run --help`, consultar los modelos disponibles en OpenCode Zen y confirmar que el elegido es gratuito; no inferir el coste solo por el nombre. Invocar `opencode run` desde la raíz con `--model` y el identificador elegido, título de etapa y el encargo. Usar `--session` o `--continue` al devolver hallazgos al mismo implementador. No usar `--auto` por defecto. Si el comando falla, registrar el bloqueo y diagnosticarlo antes de elegir otro modelo gratuito de Zen; ante cualquier duda, consultar al usuario con AskUserTool o su equivalente antes de delegar.

## Otro implementador indicado expresamente por el usuario

Verificar la CLI y el nombre del modelo en el entorno. `codex exec` acepta `-m`, `-C`, `-s` y un prompt por stdin; seleccionar `workspace-write` y conservar la revisión de permisos. No usar opciones que eviten el sandbox o las aprobaciones. Para Claude u otra herramienta, adaptar solo el comando de invocación; el contrato y la evidencia no cambian.

## Entrega

Esperar la terminación del proceso externo y revisar su código de salida, diff y registro. Si el agente deja trabajo parcial, marcarlo como tal. El director ejecuta las comprobaciones pertinentes de manera independiente y registra su propia revisión. Reenviar hallazgos concretos al mismo implementador; no iniciar otra etapa durante la iteración.
