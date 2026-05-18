# SafeContext — Resumen Ejecutivo

**Version**: 1.0.0 | **Fecha**: 2026-05-18 | **Audiencia**: CTO, CISO, Compliance Officer, Stakeholders Enterprise

---

## Tabla de Contenidos

1. [El problema que resuelve SafeContext](#1-el-problema-que-resuelve-safecontext)
2. [Que es SafeContext](#2-que-es-safecontext)
3. [Capacidades principales](#3-capacidades-principales)
4. [Diferencial competitivo](#4-diferencial-competitivo)
5. [Cumplimiento normativo](#5-cumplimiento-normativo)
6. [Arquitectura de seguridad](#6-arquitectura-de-seguridad)
7. [Integracion con su ecosistema](#7-integracion-con-su-ecosistema)
8. [SLAs y garantias operacionales](#8-slas-y-garantias-operacionales)
9. [Roadmap de madurez](#9-roadmap-de-madurez)
10. [Modelo de despliegue y requisitos](#10-modelo-de-despliegue-y-requisitos)
11. [Contacto y soporte](#11-contacto-y-soporte)

---

## 1. El problema que resuelve SafeContext

Las organizaciones empresariales estan adoptando herramientas de Inteligencia Artificial a un ritmo sin precedentes. Asistentes de codigo, sistemas de resumen documental, chatbots internos: todas estas herramientas tienen en comun que procesan documentos internos de la empresa. Y todos esos documentos contienen, en mayor o menor medida, informacion que nunca deberia salir del perimetro corporativo: nombres de clientes, numeros de identificacion, datos bancarios, credenciales de acceso, codigo propietario, informacion medica, acuerdos de confidencialidad.

El problema no es la IA en si misma. El problema es que nadie, hoy, puede demostrar de forma verificable y auditada que un documento especifico fue revisado antes de llegar a un modelo. Los equipos de seguridad no tienen visibilidad sobre que informacion fluye desde los repositorios, las bases de conocimiento y los documentos internos hacia los modelos. Los equipos de cumplimiento no tienen evidencia documentada de los controles aplicados. Y cuando un auditor pregunta "como puede usted probar que los datos personales de sus clientes no fueron enviados a un modelo de lenguaje externo", la respuesta honesta de la mayoria de organizaciones hoy es: no puedo.

Las consecuencias son serias. Una violacion de datos vehiculada a traves de un pipeline de IA puede activar obligaciones de notificacion bajo el GDPR (con multas de hasta el 4% de la facturacion global), incumplimientos de HIPAA (con sanciones civiles y penales en EEUU), fallos en auditorias SOC2, y un dano reputacional ante clientes que puede ser permanente. Las soluciones existentes, escáneres de secretos para credenciales, herramientas DLP de correo electronico, revisiones manuales ad hoc, fueron disenadas para problemas anteriores al auge de la IA generativa. No estan disenadas para el nuevo vector: el contexto documental que alimenta los modelos de lenguaje.

---

## 2. Que es SafeContext

SafeContext es la capa de gobierno de contexto para pipelines de Inteligencia Artificial.

No es un escaner de secretos (esos buscan credenciales hardcodeadas en codigo). No es un sistema DLP de correo electronico (esos controlan lo que sale por email). SafeContext es el middleware de seguridad que se ubica entre los documentos de su organizacion y los modelos de IA: cada documento que va a ser procesado por un modelo pasa primero por SafeContext, que detecta la informacion sensible, aplica las reglas de negocio de su organizacion, genera un registro inmutable y verificable de cada decision, y bloquea el pipeline si hay informacion que requiere supervision humana. El resultado es un audit trail criptograficamente firmado que le permite demostrar, ante cualquier auditor, exactamente que controles se aplicaron, cuando, y quien los autorizo.

---

## 3. Capacidades principales

| Capacidad | Descripcion en lenguaje de negocio | Garantia enterprise |
|---|---|---|
| **Deteccion automatica de informacion sensible** | Identifica automaticamente mas de 20 tipos de datos sensibles: nombres, emails, numeros de telefono, IBANs, numeros de identificacion, datos medicos, credenciales y mas, en documentos de texto en cualquier formato | Precision >= 90% verificada con conjunto de test en espanol e ingles |
| **Politica de empresa configurable** | Las reglas que determinan que informacion es inaceptable y que debe revisarse se definen en lenguaje de politica auditado, versionado en git y desplegable sin interrupcion del servicio | Politica inmutable en produccion, cualquier cambio queda registrado con autor y timestamp |
| **Revision humana obligatoria con segregacion de roles** | Cuando un documento contiene informacion de alto riesgo, un revisor designado debe aprobar o rechazar explicitamente antes de que el pipeline continue. La misma persona que submite no puede aprobar | Control SOD (Segregation of Duties) integrado, no configurable ni eludible |
| **Audit trail criptograficamente firmado** | Cada operacion genera un registro inmutable con firma HMAC que permite verificar que no fue alterado tras su creacion. El registro incluye que se encontro, quien lo reviso y que decision tomo | Evidencia presentable ante auditores externos sin necesidad de acceso al sistema |
| **Integracion con pipelines CI/CD** | Bloquea automaticamente los Pull Requests y despliegues cuando se detecta informacion sensible no revisada, sin necesidad de intervencion manual del equipo de seguridad | Compatible con GitHub Actions, GitLab CI y Azure DevOps sin modificar el pipeline existente |
| **Almacenamiento WORM de evidencias** | Los artefactos de auditoria (documentos originales y sanitizados) se almacenan con bloqueo de objetos: son inmutables durante el periodo de retencion configurado | Inmutabilidad verificable, cumple requisitos de retencion de evidencia de GDPR, HIPAA y SOC2 |
| **Gestion de claves criptograficas (KMS)** | El cifrado de artefactos usa claves gestionadas por un sistema de gestion de claves dedicado, con rotacion programada y trazabilidad completa | Claves separadas de los datos, rotacion sin tiempo de inactividad, log de acceso completo |
| **Monitoreo y SLO integrados** | Dashboards operacionales en tiempo real con alertas automaticas ante degradacion del servicio, consumo del error budget y anomalias de deteccion | SLO de disponibilidad 99.9% con metricas publicas auditables |

---

## 4. Diferencial competitivo

### SafeContext vs DLP tradicional

Las soluciones DLP (Data Loss Prevention) existentes fueron disenadas para controlar flujos de datos estructurados a traves de canales conocidos: email, transferencias de archivos, impresoras. No tienen capacidad para:

- Analizar el contexto semantico de documentos que van a ser enviados a un modelo de lenguaje
- Integrarse en el flujo de desarrollo de software (CI/CD pipelines)
- Generar evidencia de auditoria especifica para el uso de IA generativa
- Aplicar reglas de negocio complejas con logica condicional auditada

SafeContext no reemplaza el DLP corporativo. Lo complementa en el dominio especifico donde los DLP actuales tienen punto ciego: el pipeline de IA.

### SafeContext vs escáneres de secretos

Los escáneres de secretos (tipo GitGuardian, Trufflehog) buscan patrones de credenciales hardcodeadas en codigo fuente: API keys, tokens, contrasenas. Son herramientas de nicho para un problema especifico. SafeContext detecta un espectro mucho mas amplio de informacion sensible (datos personales, datos medicos, datos financieros, informacion corporativa confidencial) y ademas gestiona el flujo de aprobacion, genera evidencia auditable y aplica politica de empresa. No son soluciones comparables.

### SafeContext vs sanitizacion manual

La revision manual de documentos antes de enviarlos a un modelo de IA es el proceso actual en muchas organizaciones. Sus limitaciones son fundamentales:

- No es escalable: con equipos de decenas o cientos de personas usando herramientas de IA, la revision manual es un cuello de botella operativo
- No es verificable: no hay evidencia de que la revision se hizo, quien la hizo, o que criterios se aplicaron
- No es consistente: diferentes revisores toman decisiones diferentes sobre el mismo tipo de informacion
- No es auditable: ante un auditor externo, "revisamos manualmente" no es una respuesta aceptable como control

SafeContext automatiza el 80-90% de las decisiones mediante politica configurable y reserva la revision humana para los casos que genuinamente la requieren, generando evidencia verificable en cada paso.

### SafeContext vs no hacer nada

El escenario de riesgo sin SafeContext en un entorno con uso activo de IA generativa incluye: exposicion de datos personales de clientes a modelos de terceros sin base legal bajo GDPR, incumplimiento de controles de auditoria bajo SOC2 (especificamente CC6.1, CC6.6), imposibilidad de demostrar conformidad con el principio de minimizacion de datos, y ausencia de evidencia en caso de investigacion por parte de una autoridad de proteccion de datos.

---

## 5. Cumplimiento normativo

SafeContext ha sido disenado desde sus fundamentos para servir como control tecnico verificable bajo los principales marcos de cumplimiento normativo.

### GDPR (Reglamento General de Proteccion de Datos)

| Articulo | Requisito | Como SafeContext lo cubre |
|---|---|---|
| Art. 5 — Principios de tratamiento | Minimizacion de datos: solo procesar los datos estrictamente necesarios | SafeContext detecta y segrega los datos personales antes de que lleguen al modelo, documentando cada decision |
| Art. 17 — Derecho al olvido | Capacidad de demostrar que datos de un interesado no fueron procesados por IA | El audit trail permite buscar por tipo de dato y demostrar ausencia de tratamiento, o el alcance exacto del tratamiento realizado |
| Art. 25 — Privacidad desde el diseno | Los controles de privacidad deben ser tecnicos, no solo procedimentales | SafeContext es un control tecnico integrado en el pipeline, no una politica de empresa que depende del cumplimiento voluntario |
| Art. 30 — Registro de actividades | Documentacion de las actividades de tratamiento | El audit trail de SafeContext es un registro continuo y automatico de cada operacion de tratamiento de datos via IA |

### HIPAA (Health Insurance Portability and Accountability Act)

| Control | Como SafeContext lo cubre |
|---|---|
| Audit Controls (§164.312(b)) | Log de auditoria inmutable con timestamp, actor y decision para cada operacion |
| Integrity (§164.312(c)) | Firma criptografica HMAC en cada registro; deteccion de informacion de salud protegida (PHI) con alta precision |
| Transmission Security (§164.312(e)) | Cifrado en transito (TLS) y en reposo (AES via Vault KMS) para todos los artefactos |
| Minimum Necessary Standard | La politica configurable permite definir exactamente que PHI nunca debe llegar a un modelo |

### SOC2 Type II

| Criterio | Como SafeContext lo cubre |
|---|---|
| CC6.1 — Logical access | Autenticacion SSO con MFA obligatorio; RBAC con roles granulares |
| CC6.6 — Data classification | Deteccion y clasificacion automatica de informacion sensible en cada operacion |
| CC7.2 — System monitoring | Alertas automaticas, dashboards de SLO, audit trail continuo |

### ISO 27001

SafeContext es un control tecnico que contribuye a los objetivos de los dominios A.8 (Gestion de activos de informacion), A.9 (Control de acceso), A.12 (Seguridad en las operaciones) y A.18 (Cumplimiento). El audit trail con firma criptografica proporciona la evidencia documental que los auditores ISO 27001 requieren para verificar que los controles no solo existen en papel sino que se aplican en la practica.

---

## 6. Arquitectura de seguridad

SafeContext implementa una arquitectura de tres capas diseñada para garantizar que ninguna informacion sensible llega a los modelos de IA sin haber pasado por controles documentados.

```
╔══════════════════════════════════════════════════════════════════╗
║                    CAPA 1: DOCUMENTOS                           ║
║                                                                  ║
║   Repositorios de codigo   Bases de conocimiento   Documentos   ║
║   corporativos             y wikis internas         de contexto  ║
╚══════════════════════════════════════════════════════════════════╝
                              │
                              │ Todo el contexto pasa por aqui
                              ▼
╔══════════════════════════════════════════════════════════════════╗
║                   CAPA 2: SAFECONTEXT                           ║
║                                                                  ║
║   Deteccion de PII   →   Evaluacion de politica   →   Decision  ║
║                                                                  ║
║   ┌────────────────────────────────────────────────────────┐    ║
║   │  Automatico: aprobado                                  │    ║
║   │  Requiere revision: esperar decision humana            │    ║
║   │  Rechazado: pipeline bloqueado                         │    ║
║   └────────────────────────────────────────────────────────┘    ║
║                                                                  ║
║   Genera: Audit trail firmado + Artefactos inmutables           ║
╚══════════════════════════════════════════════════════════════════╝
                              │
                              │ Solo contexto aprobado y sanitizado
                              ▼
╔══════════════════════════════════════════════════════════════════╗
║                   CAPA 3: MODELOS DE IA                         ║
║                                                                  ║
║   Claude (Anthropic)   GitHub Copilot   Codex   LLMs propios    ║
║                                                                  ║
║   El modelo recibe el contexto con la informacion sensible       ║
║   reemplazada por etiquetas neutrales, nunca los datos reales.  ║
╚══════════════════════════════════════════════════════════════════╝
```

**Lo que ocurre en cada capa**:

**Capa 1 — Documentos**: Los documentos existen en sus ubicaciones habituales. SafeContext no requiere cambiar donde se almacenan ni como se gestionan. Lo unico que cambia es que antes de fluir hacia un modelo, pasan por la capa 2.

**Capa 2 — SafeContext**: El nucleo de la plataforma. Aqui ocurren tres cosas en cada operacion: (1) deteccion de informacion sensible mediante modelos de lenguaje especializados, (2) evaluacion contra la politica de empresa para determinar si la informacion es aceptable o requiere revision, y (3) generacion del registro inmutable de la decision. Esta capa es completamente auditable y genera evidencia verificable.

**Capa 3 — Modelos de IA**: Los modelos reciben el contexto ya evaluado y, si corresponde, sanitizado. La informacion sensible ha sido reemplazada por etiquetas neutrales. El modelo puede trabajar con el contexto sin que los datos reales salgan del perimetro corporativo.

---

## 7. Integracion con su ecosistema

### Modelos de IA compatibles

SafeContext es compatible con cualquier modelo de lenguaje que soporte el protocolo MCP (Model Context Protocol):

- **Claude** (Anthropic) — integracion nativa via MCP
- **GitHub Copilot** — via extension de VSCode con MCP
- **OpenAI Codex / GPT-4** — via servidor MCP
- **Modelos propios** (LLaMA, Mistral, etc.) — via cliente MCP generico
- **Cualquier LLM** — cualquier sistema que consuma contexto documental puede integrarse

### Plataformas de CI/CD compatibles

| Plataforma | Tipo de integracion | Esfuerzo de integracion |
|---|---|---|
| GitHub Actions | Action oficial disponible en marketplace | Menos de 1 hora — anadir 3 lineas al workflow existente |
| GitLab CI | Script de integracion disponible | Menos de 1 hora — anadir stage al `.gitlab-ci.yml` |
| Azure DevOps | Task de pipeline disponible | Menos de 2 horas — anadir task al pipeline YAML |
| Jenkins | Plugin disponible | 2-4 horas — instalar plugin y configurar step |
| Cualquier CI/CD | API REST estandar | Horas — llamar al endpoint `/v1/mcp/tools/safecontext.scan` via curl |

### Opciones de despliegue

| Modalidad | Descripcion | Disponible |
|---|---|---|
| **On-premise** | Desplegado en infraestructura propia del cliente. Sin datos saliendo del perimetro corporativo. | Disponible ahora |
| **Air-gapped** | Operacion completamente desconectada de internet. Sin dependencias externas en produccion. Los modelos de deteccion se distribuyen como paquetes offline. | Fase 5 (roadmap) |
| **Cloud privada** | Desplegado en VPC dedicada del cliente (AWS, Azure, GCP). Gestionado por el equipo de SafeContext o por el equipo del cliente. | Disponible ahora |

SafeContext no opera un SaaS compartido. Cada despliegue es dedicado al cliente, sin datos compartidos entre organizaciones.

---

## 8. SLAs y garantias operacionales

| Metrica | Objetivo | Metodo de medicion |
|---|---|---|
| **Disponibilidad** | 99.9% mensual (< 43.8 minutos de downtime al mes) | Prometheus uptime, dashboard Grafana con historial de 90 dias |
| **Latencia de scan** | p95 < 5 segundos para documentos de hasta 1 MB | Histograma Prometheus, percentil 95 en ventana deslizante de 5 minutos |
| **RTO (Recovery Time Objective)** | < 15 minutos desde la deteccion del fallo hasta el sistema operativo | Verificado en drill trimestral de Disaster Recovery |
| **RPO (Recovery Point Objective)** | < 5 minutos de perdida de datos en el peor caso | Garantizado por WAL archiving de PostgreSQL en configuracion de produccion |
| **Precision de deteccion** | Recall >= 90% para entidades principales (PERSON, EMAIL, PHONE, IBAN) | Medido continuamente en Prometheus, alerta si baja de 85% |
| **Inmutabilidad del audit trail** | 100% — ningun registro puede modificarse tras su creacion | Garantizado por Object Locking WORM en MinIO + firma HMAC verificable |

### Verificacion independiente

Los SLAs son medibles de forma independiente por el equipo del cliente:

- Las metricas de disponibilidad y latencia son accesibles en tiempo real via Prometheus (`/metrics`)
- El dashboard de Grafana muestra el historial completo de los ultimos 90 dias
- El drill de Disaster Recovery se realiza trimestralmente con evidencia documentada

---

## 9. Roadmap de madurez

SafeContext se desarrolla en cinco fases que progresivamente amplian la cobertura y los controles disponibles.

| Fase | Nombre | Capacidades principales | Estado |
|---|---|---|---|
| **F1** | Base | Deteccion de PII, politica OPA, audit trail firmado, revision humana, integracion GitHub Actions, MFA/SSO | En desarrollo |
| **F2** | Producto | Dashboard de compliance con metricas de SLO, gestion de politicas via UI, notificaciones en tiempo real, reporte ejecutivo automatico | Planificada |
| **F3** | Supply Chain | Escaneo de dependencias de terceros, analisis de documentos de proveedores, gestion de cadena de suministro de contexto IA | Planificada |
| **F4** | Enterprise | SSO con SAML 2.0, integracion con SIEM (Splunk, Elastic), API de gestion multi-tenant, soporte para GitLab CI y Azure DevOps nativo | Planificada |
| **F5** | Air-gapped | Operacion completamente offline, modelos de deteccion distribuidos como paquetes firmados, sin dependencias de internet en ningun componente | Planificada |

Las fases son aditivas: cada fase mantiene todas las capacidades de las fases anteriores.

---

## 10. Modelo de despliegue y requisitos

### Requisitos de hardware

| Recurso | Minimo (evaluacion / desarrollo) | Recomendado (produccion) |
|---|---|---|
| RAM | 4 GB | 16 GB |
| CPU | 2 nucleos | 8 nucleos |
| Almacenamiento | 20 GB | 200 GB (para audit trail a largo plazo) |

### Requisitos de software

La unica dependencia de software en el servidor del cliente es **Docker**. Todos los componentes de SafeContext se distribuyen como contenedores Docker. No hay dependencias de lenguajes de programacion, runtimes, gestores de paquetes ni instaladores en el sistema operativo del host.

### Conectividad de red

SafeContext no requiere conectividad a internet durante la operacion. Los modelos de deteccion de PII se distribuyen como parte de las imagenes Docker. Una vez descargadas las imagenes, el sistema opera completamente dentro del perimetro corporativo.

La unica conectividad requerida es interna entre los contenedores del stack (gestionada automaticamente por Docker) y la accesibilidad de los puertos de servicio desde las maquinas de los usuarios y los agentes de CI/CD.

### Soporte air-gapped

La Fase 5 del roadmap incluye la certificacion formal para despliegues air-gapped, incluyendo el procedimiento de distribucion offline de actualizaciones de modelos, la verificacion criptografica de integridad de los paquetes de actualizacion, y la documentacion de procedimientos para entornos con politicas de red mas restrictivas.

---

## 11. Contacto y soporte

**Repositorio del proyecto**: https://github.com/oscarives/safeContext

**Mantenedor principal**: Oscar Rivas (oscarives@gmail.com)

**Para consultas comerciales y de despliegue enterprise**: Contactar a traves del repositorio de GitHub abriendo un Issue con la etiqueta `enterprise-inquiry`.

**Documentacion tecnica adicional**:

- Manual de Operacion: `docs/manuals/02_OPERACION.md`
- Manual de Usuario: `docs/manuals/03_USUARIO.md`
- Referencia de API: `docs/manuals/04_API.md` (en preparacion)
- Runbooks operacionales: `docs/runbooks/`

---

*SafeContext Resumen Ejecutivo v1.0.0 — 2026-05-18*
*Confidencial — Distribucion restringida a stakeholders autorizados.*
