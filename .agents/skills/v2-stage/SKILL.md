---
name: v2-stage
description: Define, delegate, review, and close one Autocrop V2 stage when the user explicitly invokes this workflow.
---

# Dirigir una etapa V2

Usar esta skill solo para una etapa concreta de `.plans/v2/` y el rol pedido por el usuario. Leer `AGENTS.md`, `.plans/v2/PLAN.md`, el contrato y el código pertinente. Mantener `plan.md` como contrato y estado, y `registro.md` como evidencia e historial de revisión.

## Definir

Redactar el contrato de la etapa con los criterios y la validación necesarios para implementarla sin inventar decisiones de producto. Crear el registro con secciones Implementación y Revisión vacías. Presentar el contrato al usuario y esperar su aprobación explícita antes de encargar código. No iniciar la etapa siguiente automáticamente.

## Delegar y revisar

Tras la aprobación, usar el implementador indicado por el usuario o OpenCode Muse por defecto. Un agente externo se invoca mediante su CLI; no asumir que una herramienta de subagentes de Codex o Claude puede cambiar de proveedor. Ver [invocación de implementadores](references/implementers.md) para el traspaso. Dar al implementador una etapa completa y pedir tests primero, evidencia roja funcional, implementación mínima, suite verde y registro de resultados. Evitar encargos simultáneos que editen los mismos archivos.

El mismo director revisa el diff completo, el contrato frente a los tests, la evidencia y los casos límite. Registrar cada hallazgo con ubicación, impacto, criterio y corrección esperada. Pedir la regresión antes de cada corrección. Cerrar la etapa solo cuando todos los criterios estén verificados; si falta una comprobación, registrar el bloqueo y mantener `en revisión`.

## Límites

Respetar autorizaciones y permisos del entorno; no usar flags que desactiven controles de aprobación o sandbox. No atribuir al implementador resultados que el director no pueda corroborar. Conservar la evidencia previa al iterar. Informar al usuario del cierre o bloqueo con enlace al plan.
