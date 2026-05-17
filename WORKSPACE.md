# WORKSPACE.md · SafeContext — Estructura y delegación
**Versión**: 0.1.0 · **Fecha**: 2026-05-17
**Propósito**: instrucciones para compartir esta carpeta con Claude Code y arrancar el proyecto.

---

## Estructura del workspace

```
safecontext/
├── AGENTS.md                    ← System prompt de Claude Code (leer primero)
├── WORKSPACE.md                 ← Este archivo
│
├── docs/
│   ├── DOC-0_UNIFIED.md         ← Fuente de verdad (leer antes que todo)
│   ├── DOC-1_PRD.md             ← Requisitos funcionales y no funcionales
│   ├── DOC-2_SAD.md             ← Arquitectura, ADRs, modelo de datos
│   ├── DOC-3_SPEC.md            ← Spec ejecutable — entrada al backlog
│   ├── SKILLS.md                ← Habilidades por dominio de agente
│   └── research/
│       └── deep-research-report.md  ← Análisis de madurez (contexto y justificación)
│
├── apps/
│   ├── api/                     ← FastAPI backend + MCP Server
│   └── ui/                      ← Next.js frontend
│
├── workers/                     ← Dramatiq workers (agentes internos)
│   ├── detector/
│   ├── sanitizer/
│   ├── classifier/
│   ├── auditor/
│   └── reviewer/
│
├── policies/                    ← Políticas OPA/Rego
│   ├── base.rego
│   └── tests/
│
├── infra/
│   ├── docker-compose.yml       ← Stack completo F1-F2
│   ├── kubernetes/              ← Manifiestos K8s F3+
│   ├── minio/                   ← Configuración MinIO
│   └── otel/                    ← OTel Collector config
│
├── migrations/                  ← Alembic migrations
│
├── tests/
│   ├── fixtures/
│   │   └── corpus/              ← Corpus etiquetado para evaluación de detectores
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── .github/
    └── workflows/               ← GitHub Actions (pipeline gate, CI/CD)
```

---

## Cómo delegar a Claude Code

### Paso 1: Compartir la carpeta

En Claude Code, ejecuta:
```bash
# Desde el directorio donde descargaste el workspace
claude --context ./safecontext/
```

O si usas la integración de carpeta:
- Abre Claude Code
- Selecciona "Open folder" → selecciona la carpeta `safecontext/`
- Claude Code indexará todos los archivos

### Paso 2: Instrucción de arranque

Copia y pega este prompt como primer mensaje a Claude Code:

```
Lee los siguientes documentos en este orden antes de cualquier acción:
1. AGENTS.md
2. docs/DOC-0_UNIFIED.md
3. docs/DOC-1_PRD.md
4. docs/DOC-2_SAD.md
5. docs/DOC-3_SPEC.md
6. docs/SKILLS.md

Una vez leídos, genera el plan completo de desarrollo de SafeContext:
- Roadmap por fases con fechas estimadas
- Historias de usuario y tareas técnicas por cada entregable de DOC-3
- Identificación de dependencias y paralelismo
- Número de agentes especializados por fase y su asignación
- Orden de ejecución optimizado para maximizar paralelismo sin conflictos

No generes código todavía. Primero presenta el plan para revisión.
```

### Paso 3: Revisión del plan

Claude Code presentará el plan. Revisá:
- Que todos los entregables de DOC-3 estén cubiertos
- Que el orden de fases sea correcto (F1 completo antes de F2)
- Que los agentes asignados sean coherentes con AGENTS.md
- Que las dependencias estén correctamente identificadas

Una vez aprobado el plan:
```
El plan está aprobado. Inicia la ejecución de F1.
Comienza por E1.1 (repositorio y estructura) y E1.2 (schema de base de datos) en paralelo.
```

---

## Reglas de trabajo con Claude Code

### Lo que Claude Code hace autónomamente
- Lee y analiza todos los documentos del workspace
- Genera código, tests y configuración
- Ejecuta tests y reporta resultados
- Propone cambios con análisis de impacto

### Lo que Claude Code te consulta antes de hacer
- Cambios a schemas de base de datos
- Cambios a interfaces públicas (API, MCP tools)
- Cambios a políticas OPA en producción
- Uso de sub-agentes no planificados en la fase actual

### Cómo mantener el contexto entre sesiones

Al inicio de cada sesión nueva con Claude Code:
```
Resumen del estado actual del proyecto:
- Fase activa: F{n}
- Último entregable completado: E{n}.{m}
- Gates de fase cumplidos: [lista]
- Pendiente en la sesión actual: [descripción]
```

Claude Code puede generar este resumen al final de cada sesión para que lo uses en la siguiente.

---

## Cómo agregar el informe de madurez como contexto

El archivo `docs/research/deep-research-report.md` debe estar en la carpeta compartida con Claude Code. Este archivo:
- Justifica las decisiones en los ADRs
- Explica los riesgos y sus mitigaciones
- Provee contexto para preguntas que no están respondidas en los documentos de definición

Claude Code lo consulta cuando necesita entender el "por qué" de una decisión, no el "qué".

---

## Métricas de progreso del proyecto

Claude Code mantiene este registro actualizado al completar cada entregable:

| Entregable | Estado | Evidencia | Fecha |
|---|---|---|---|
| E1.1 Repositorio | ⬜ Pendiente | — | — |
| E1.2 Schema DB | ⬜ Pendiente | — | — |
| E1.3 Backend API | ⬜ Pendiente | — | — |
| E1.4 MCP Server | ⬜ Pendiente | — | — |
| E1.5 Workers | ⬜ Pendiente | — | — |
| E1.6 Policy Engine | ⬜ Pendiente | — | — |
| E1.7 Observabilidad | ⬜ Pendiente | — | — |
| E1.8 Pipeline Gate | ⬜ Pendiente | — | — |
| E1.9 Infra Compose | ⬜ Pendiente | — | — |
| **Gate F1** | ⬜ Pendiente | — | — |
| E2.1 Auditoría | ⬜ Pendiente | — | — |
| E2.2 MinIO WORM | ⬜ Pendiente | — | — |
| E2.3 Workers resilientes | ⬜ Pendiente | — | — |
| E2.4 Backup/DR | ⬜ Pendiente | — | — |
| E2.5 Cache distribuido | ⬜ Pendiente | — | — |
| E2.6 Revisión humana UI | ⬜ Pendiente | — | — |
| E2.7 MCP tools adicionales | ⬜ Pendiente | — | — |
| **Gate F2** | ⬜ Pendiente | — | — |

*(Claude Code actualiza esta tabla con ✅ y la evidencia al completar cada ítem)*

---

*Este workspace está listo para ser delegado a Claude Code.*
*Todo lo necesario para arrancar el proyecto está en esta carpeta.*
