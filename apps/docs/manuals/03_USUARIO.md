# SafeContext — Manual de Usuario

**Versión**: 2.0.0 | **Fecha**: 2026-05-25 | **Audiencia**: Compliance, Revisores, Tech Leads
**Documentos relacionados**: [Manual 08 — Roles y Permisos](./08_ROLES_Y_PERMISOS.md), [Manual 07 — Administración](./07_ADMIN_CONFIGURACION.md)

---

## Tabla de Contenidos

1. [Introduccion](#1-introduccion)
2. [Acceso al sistema](#2-acceso-al-sistema)
3. [Dashboard principal](#3-dashboard-principal)
4. [Escanear un documento](#4-escanear-un-documento)
5. [Revision humana de hallazgos](#5-revision-humana-de-hallazgos)
6. [Exportar evidencia de auditoria](#6-exportar-evidencia-de-auditoria)
7. [Gestion de politicas (PolicyEditor)](#7-gestion-de-politicas-policyeditor)
8. [Casos de uso frecuentes](#8-casos-de-uso-frecuentes)
9. [Glosario para usuarios de negocio](#9-glosario-para-usuarios-de-negocio)

---

## 1. Introduccion

### Que hace SafeContext

SafeContext es una plataforma de gobierno de documentos para Inteligencia Artificial. Cuando tu equipo usa modelos de IA (como Claude, GitHub Copilot o cualquier LLM) para procesar documentos internos, existe el riesgo de que informacion sensible, como datos personales, credenciales, o informacion financiera, llegue al modelo sin revision previa.

SafeContext actua como un intermediario de seguridad: cada documento que ingresa al pipeline de IA pasa primero por SafeContext, que detecta la informacion sensible, la registra con trazabilidad completa y, si es necesario, requiere una revision humana antes de continuar.

El resultado es un **registro de auditoria inmutable y verificable** de cada operacion: que documento fue procesado, que informacion sensible se encontro, quien lo aprobo y cuando. Esta evidencia es presentable ante auditores de cumplimiento normativo (GDPR, HIPAA, SOC2).

### Roles y sus responsabilidades

| Rol | Quien lo usa habitualmente | Para que | Paginas accesibles |
|---|---|---|---|
| **viewer** | Cualquier miembro del equipo | Ver el estado del sistema, enviar escaneos y consultar historial de operaciones | `/dashboard`, `/scan`, `/audit` |
| **reviewer** | Compliance Officer, revisor designado | Aprobar o rechazar hallazgos que requieren revision humana. Sujeto a SoD | `/dashboard`, `/scan`, `/audit`, `/review` |
| **policy_editor** | Tech Lead, Security Lead | Gestionar waivers (excepciones de politica) con justificacion documentada | `/dashboard`, `/scan`, `/audit`, `/admin/waivers` |
| **admin** | SRE, DevOps, Administrador | Gestion completa: tenants, SIEM, retencion, waivers, purga GDPR, todas las funciones | Todas las paginas incluyendo `/admin/*` |

> Para la matriz completa de permisos por endpoint REST y tool MCP, ver [Manual 08 — Roles y Permisos](./08_ROLES_Y_PERMISOS.md).

> **Regla de segregacion de funciones**: El mismo usuario que submite un documento para scan NO puede aprobar sus propios hallazgos. Esta restriccion es automatica y no puede desactivarse.

---

## 2. Acceso al sistema

### URL de acceso

```
http://[host]:8088
```

En entorno de desarrollo local: `http://localhost:8088`

### Login con SSO (Keycloak)

SafeContext no gestiona contrasenas propias. La autenticacion es delegada a Keycloak SSO, lo que significa que usas las mismas credenciales corporativas.

**Proceso de login**:

1. Navegar a `http://[host]:8088`
2. La aplicacion te redirige automaticamente a la pantalla de login de Keycloak
3. Introducir el correo electronico corporativo y la contrasena
4. Si es el primer acceso, Keycloak puede solicitar cambio de contrasena temporal
5. Tras la autenticacion, Keycloak redirige de vuelta a SafeContext con la sesion activa
6. La pantalla principal muestra el Dashboard con tu rol asignado en la esquina superior derecha

**Duracion de la sesion**: 8 horas. Tras la expiracion, seras redirigido al login automaticamente.

### MFA obligatorio — Configuracion de TOTP

La autenticacion multifactor (MFA) es obligatoria para los roles Reviewer, PolicyEditor y Admin.

**Como configurar TOTP**:

1. En Keycloak, tras el primer login, aparece la pantalla "Configurar autenticador"
2. Seleccionar "Authenticator Application"
3. Abrir tu aplicacion de autenticador (Google Authenticator, Authy, Microsoft Authenticator)
4. En la aplicacion, agregar cuenta nueva escaneando el codigo QR que muestra Keycloak
5. Ingresar el codigo de 6 digitos que muestra la app para confirmar la configuracion
6. Guardar los codigos de recuperacion en un lugar seguro (son de un solo uso para recuperacion de emergencia)

**En cada login posterior**: tras ingresar usuario y contrasena, Keycloak solicita el codigo TOTP de 6 digitos actual.

Si pierdes acceso al autenticador, contactar al Administrador del sistema para que resetee tu configuracion MFA.

### Roles y permisos detallados

| Accion | Viewer | Reviewer | PolicyEditor | Admin |
|---|---|---|---|---|
| Ver dashboard de estado | Si | Si | Si | Si |
| Ver historial de operaciones | Si | Si | Si | Si |
| Ver detalle de hallazgos | Si | Si | Si | Si |
| Exportar audit trail | Si | Si | Si | Si |
| Aprobar/rechazar hallazgos | No | Si | No | Si |
| Ver politica OPA activa | No | Si | Si | Si |
| Modificar politica OPA | No | No | Si | Si |
| Gestionar usuarios | No | No | No | Si |
| Acceder a configuracion del sistema | No | No | No | Si |
| Subir documentos via API | Si* | Si* | Si* | Si |

*Con token de API valido generado para su cuenta.

---

## 3. Dashboard principal

**URL**: `/dashboard`

El dashboard es la pantalla de inicio tras el login. Proporciona una vision de estado del sistema en tiempo real.

### Indicadores de estado del sistema

La fila superior muestra el estado de cada componente critico con un indicador de color:

- **Verde**: componente saludable y operativo
- **Amarillo**: degradado, funcional pero con alertas activas
- **Rojo**: componente no disponible o con error critico

Componentes monitoreados: API, Base de datos, Cola de mensajes (Redis), Almacenamiento (MinIO), Motor de politicas (OPA), Detector de PII (Presidio).

### Panel de actividad reciente

Muestra las ultimas 10 operaciones de scan con:
- Fecha y hora
- Nombre del documento o identificador del artefacto
- Estado: `approved`, `rejected`, `pending_review`, `processing`
- Resultado: numero de hallazgos detectados
- Link al detalle de la operacion

### Metricas de las ultimas 24 horas

- Total de operaciones procesadas
- Documentos aprobados automaticamente
- Documentos pendientes de revision humana
- Tiempo promedio de procesamiento

### Links rapidos

Desde el dashboard puedes acceder directamente a:
- **Revision pendiente** (`/review`): contador con los hallazgos que esperan tu revision
- **Audit Trail** (`/audit`): busqueda de evidencia de auditoria
- **Grafana** (`http://[host]:3001`): metricas detalladas del sistema

---

## 4. Escanear un documento

El scan se realiza tipicamente de forma automatica desde pipelines CI/CD. Esta seccion describe como interactuar con el sistema tanto programaticamente como desde el pipeline.

### 4.1 Via API (curl)

Para escanear un documento de forma manual o desde un script:

```bash
# Paso 1: Obtener un token de acceso
TOKEN=$(curl -s -X POST "http://localhost:8080/realms/safecontext/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=safecontext-api&username=TU_USUARIO&password=TU_CONTRASENA" \
  | jq -r '.access_token')

# Paso 2: Enviar el documento para scan
curl -s -X POST "http://localhost:8000/v1/mcp/tools/safecontext.scan" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "El empleado Juan Garcia con DNI 12345678A tiene salario de 45000 EUR",
    "content_type": "text/plain",
    "metadata": {
      "source": "manual-test",
      "author": "tu.nombre@empresa.com"
    }
  }' | jq .
```

**Respuesta de ejemplo**:

```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "operation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending_review",
  "policy_version": "1.0.0",
  "artifact_digest": "sha256:abc123...",
  "findings": [
    {
      "entity_type": "PERSON",
      "text": "Juan Garcia",
      "start": 11,
      "end": 22,
      "score": 0.95,
      "severity": "medium"
    },
    {
      "entity_type": "NIF",
      "text": "12345678A",
      "start": 31,
      "end": 40,
      "score": 0.99,
      "severity": "high"
    }
  ],
  "requires_human_review": true,
  "redacted_content": "El empleado [PERSON] con DNI [NIF] tiene salario de [MONEY] EUR"
}
```

### 4.2 Via GitHub Actions

El pipeline de CI/CD ejecuta el scan automaticamente en cada Pull Request que modifique archivos de contexto de IA (prompts, embeddings, documentos de conocimiento).

**Como ver el resultado en el PR**:

1. Abrir el Pull Request en GitHub
2. En la seccion "Checks", buscar el check llamado `SafeContext Security Scan`
3. Si el check es verde: el scan paso, no se detectaron hallazgos de severidad alta/critica que requieran revision
4. Si el check es amarillo: hay hallazgos pendientes de revision humana. El PR no puede mergearse hasta que un Reviewer apruebe o rechace
5. Si el check es rojo: el scan fallo o se encontro un hallazgo critico rechazado
6. En el comentario automatico del bot de SafeContext en el PR se muestra el `trace_id` y un resumen de los hallazgos

Para ver el detalle completo, usar el `trace_id` del comentario en la seccion [6.1](#61-buscar-por-trace_id).

### 4.3 Interpretar resultados

#### Campos de la respuesta

| Campo | Tipo | Descripcion |
|---|---|---|
| `trace_id` | UUID | Identificador unico e inmutable de esta operacion. Usar para busquedas de auditoria. |
| `operation_id` | UUID | ID interno en la base de datos de SafeContext. |
| `status` | string | Estado actual de la operacion (ver tabla de estados abajo). |
| `policy_version` | string | Version de la politica OPA que evaluo esta operacion. |
| `artifact_digest` | string | Hash SHA-256 del documento original. Prueba de que el documento no fue alterado. |
| `findings` | array | Lista de hallazgos detectados. Puede estar vacia si no se detecta nada. |
| `requires_human_review` | boolean | `true` si algun hallazgo supera el umbral de revision humana. |
| `redacted_content` | string | Version del contenido con las entidades detectadas reemplazadas por etiquetas. |

#### Estados de una operacion

| Estado | Significado | Accion requerida |
|---|---|---|
| `processing` | El documento esta siendo analizado | Esperar (tipicamente < 5 segundos) |
| `approved` | Aprobado (automatico o por Reviewer) | Ninguna — el pipeline puede continuar |
| `rejected` | Rechazado — contiene PII no autorizada | El pipeline es bloqueado. Revisar hallazgos. |
| `pending_review` | Esperando decision de un Reviewer | Un Reviewer debe actuar en `/review` |

#### Severidades de hallazgos

| Severidad | Descripcion | Implicacion operacional |
|---|---|---|
| `low` | Posible informacion sensible con confianza < 70% | Registrado, no bloquea. Revision opciones. |
| `medium` | Informacion sensible con confianza 70-89% | Registrado. Puede requerir revision segun politica. |
| `high` | Informacion claramente sensible (nombre, email, telefono, IBAN) | Requiere revision humana segun politica base. |
| `critical` | Credenciales, secretos, datos medicos, datos financieros de alto riesgo | Siempre requiere revision humana. Bloquea el pipeline. |

#### Que hacer si `requires_human_review: true`

1. Anotar el `trace_id` de la respuesta
2. Navegar a `http://[host]:8088/review`
3. Buscar la operacion por `trace_id` o esperar a que aparezca en la lista de pendientes
4. Revisar cada hallazgo (ver seccion [5](#5-revision-humana-de-hallazgos))
5. Aprobar o rechazar con justificacion documentada
6. El pipeline se desbloquea automaticamente tras la decision del Reviewer

---

## 5. Revision humana de hallazgos

**URL**: `/review`

La revision humana es el mecanismo de control que garantiza que ningun documento con informacion sensible de alto riesgo llega a un modelo de IA sin supervision humana.

### 5.1 Cuando aparece un hallazgo para revisar

Un hallazgo requiere revision humana cuando se cumple cualquiera de estas condiciones:

- La severidad del hallazgo es `critical`
- La severidad del hallazgo es `high` Y la confianza del detector supera el umbral configurado en la politica OPA (por defecto: 0.75)
- La confianza del detector esta entre 0.50 y 0.75 Y la politica marca la entidad como "siempre revisar" (ej. datos medicos, datos financieros)

Los hallazgos con confianza < 0.50 se registran automaticamente como `low` y no requieren revision humana, aunque si quedan en el audit trail.

### 5.2 Como aprobar un hallazgo

Aprobar un hallazgo significa que el Reviewer ha evaluado el contenido, considera que el hallazgo es correcto y que el documento PUEDE ser procesado por el modelo de IA (o que el hallazgo fue correctamente sanitizado).

**Proceso paso a paso**:

1. Navegar a `/review`
2. En la lista de "Pendientes de revision", hacer clic en el hallazgo a evaluar
3. Se abre el panel de detalle con:
   - El **span destacado** en el texto original (el fragmento exacto que activo la deteccion)
   - El tipo de entidad detectada (PERSON, EMAIL, IBAN, etc.)
   - La confianza del detector (porcentaje)
   - La justificacion tecnica de la deteccion
   - El contenido redactado propuesto
4. Leer cuidadosamente el fragmento destacado en contexto
5. Evaluar si la deteccion es correcta
6. En el campo "Decision y justificacion", escribir la razon de la aprobacion (obligatorio, minimo 20 caracteres)
   - Ejemplo: "Nombre de persona en documento de prueba anonimizado. No contiene datos reales."
7. Hacer clic en "Aprobar"
8. La operacion cambia a estado `approved` y el pipeline se desbloquea

> **Importante**: Tu nombre, el timestamp y la justificacion quedan registrados de forma inmutable en el audit trail. Esta es la evidencia que se presenta ante auditores.

### 5.3 Como rechazar un hallazgo

Rechazar un hallazgo significa que el Reviewer determina que el documento NO debe procesarse por el modelo de IA en su estado actual, o que el hallazgo detecta un dato que genuinamente no debe salir del perimetro corporativo.

**Cuando rechazar**:

- El documento contiene datos personales reales de clientes o empleados
- El documento contiene credenciales, tokens de acceso o secretos
- El documento contiene informacion confidencial de negocio no autorizada para uso con IA
- La sanitizacion propuesta no es suficiente para anonimizar correctamente los datos

**Proceso**:

1. Seguir los pasos 1-5 de la seccion anterior
2. En el campo "Decision y justificacion", documentar la razon del rechazo
   - Ejemplo: "IBAN real de cliente detectado en contrato. Documento no debe procesarse con IA. Requiere anonimizacion manual."
3. Hacer clic en "Rechazar"
4. La operacion cambia a estado `rejected`
5. El pipeline queda bloqueado permanentemente para esta operacion
6. El actor que submito el documento recibe notificacion con el `trace_id` y la razon del rechazo

Tras un rechazo, el flujo correcto es que el equipo responsable anonimice manualmente el documento y lo resubmita como una nueva operacion (nuevo `trace_id`).

### 5.4 Regla de segregacion de funciones

SafeContext implementa automaticamente la separacion de roles en la revision:

- **El usuario que submite el documento** (via API o pipeline CI/CD) **NO puede aprobar ni rechazar** sus propios hallazgos
- Si un Admin intenta aprobar una operacion que el mismo creo, el sistema devuelve error `403 Forbidden`
- Esta restriccion no puede desactivarse ni ser sobreescrita por ningun rol, incluyendo Admin

Esta regla es un control interno requerido por SOC2 (CC6.1) y las mejores practicas de separacion de funciones (SoD).

---

## 6. Exportar evidencia de auditoria

**URL**: `/audit`

El modulo de auditoria permite exportar el registro inmutable de cualquier operacion para presentarlo como evidencia ante auditores internos o externos.

### 6.1 Buscar por trace_id

El `trace_id` es el identificador principal para encontrar una operacion en el audit trail.

**Donde encontrar el trace_id**:

- **En el PR de GitHub**: el bot de SafeContext agrega un comentario con el `trace_id` en cada PR escaneado
- **En la respuesta de la API**: campo `trace_id` en el JSON de respuesta del endpoint `/v1/mcp/tools/safecontext.scan`
- **En los logs del pipeline CI/CD**: buscar la linea `SafeContext scan completed - trace_id: XXXX`
- **En el dashboard de SafeContext**: columna "Trace ID" en el historial de operaciones

**Como buscar en `/audit`**:

1. Navegar a `/audit`
2. En el campo de busqueda "Trace ID", pegar el UUID completo
3. Hacer clic en "Buscar"
4. Tambien se puede filtrar por rango de fechas, estado, actor o tipo de entidad detectada

### 6.2 Interpretar el export

El export JSON contiene los siguientes campos:

| Campo | Descripcion |
|---|---|
| `operation.id` | UUID interno de la operacion |
| `operation.trace_id` | Identificador unico de trazabilidad |
| `operation.created_at` | Timestamp ISO 8601 de cuando se inicio el scan |
| `operation.completed_at` | Timestamp ISO 8601 de cuando se completo |
| `operation.status` | Estado final: `approved`, `rejected`, `pending_review` |
| `operation.actor_id` | Usuario o servicio que submito el documento |
| `operation.policy_version` | Version de la politica que se aplico |
| `findings` | Array de todos los hallazgos detectados |
| `findings[].entity_type` | Tipo de entidad (PERSON, EMAIL, IBAN, etc.) |
| `findings[].severity` | Severidad: `low`, `medium`, `high`, `critical` |
| `findings[].score` | Confianza del detector (0.0 a 1.0) |
| `findings[].review_decision` | `approved` o `rejected` (si hubo revision humana) |
| `findings[].reviewer_id` | Usuario que reviso el hallazgo |
| `findings[].reviewed_at` | Timestamp de la revision humana |
| `findings[].justification` | Texto de justificacion escrito por el Reviewer |
| `redactions` | Lista de textos redactados y sus reemplazos |
| `artifacts.original_digest` | SHA-256 del documento original |
| `artifacts.redacted_digest` | SHA-256 de la version redactada |
| `artifacts.storage_path` | Ruta en MinIO donde se almacenan los artefactos |
| `hmac_signature` | Firma HMAC-SHA256 del payload completo |

### 6.3 Verificar la firma HMAC

La firma HMAC garantiza que el registro de auditoria no fue alterado desde su creacion. Es la prueba criptografica de integridad que exigen los marcos de cumplimiento normativo.

**Para que sirve**: Si alguien modifica el JSON del export (por ejemplo, para ocultar un hallazgo o cambiar una decision), la firma HMAC resultante no coincidira con la almacenada. Un auditor puede verificar esto matematicamente.

**Como verificar la firma ante una auditoria**:

```bash
# El export JSON tiene este campo al final:
# "hmac_signature": "abc123..."

# Para verificar, recalcular el HMAC con la clave publica de verificacion:
cat audit_export_TRACE_ID.json | python3 -c "
import json, sys, hmac, hashlib

data = json.load(sys.stdin)
signature = data.pop('hmac_signature')
payload = json.dumps(data, sort_keys=True, separators=(',', ':')).encode()

# La clave de verificacion es publica y esta en /v1/audit/verification-key
verification_key = b'VERIFICATION_KEY_FROM_API'
expected = hmac.new(verification_key, payload, hashlib.sha256).hexdigest()

print('VALID' if hmac.compare_digest(signature, expected) else 'INVALID - RECORD MAY HAVE BEEN TAMPERED')
"
```

La API expone la clave de verificacion publica en `GET /v1/audit/verification-key` para que cualquier auditor pueda verificar sin acceso a secretos internos.

### 6.4 Descargar el JSON

1. Tras encontrar la operacion en `/audit`, hacer clic en "Ver detalle"
2. En la pantalla de detalle, hacer clic en el boton "Descargar JSON"
3. El archivo se descarga con el nombre `safecontext_audit_[trace_id].json`
4. Este archivo es el documento de evidencia que se adjunta en el expediente de auditoria

> **Nota**: Los exports de audit trail tienen firma HMAC incorporada. No modificar el archivo descargado, ya que cualquier cambio invalida la firma y la evidencia deja de ser verificable.

---

## 7. Gestion de politicas (PolicyEditor)

Esta seccion es para usuarios con rol **PolicyEditor** o **Admin**.

### Que es una politica OPA y para que sirve

OPA (Open Policy Agent) es el motor de decisiones que determina, para cada scan:

- Que severidad asignar a cada hallazgo segun el tipo de entidad y la confianza del detector
- Si el hallazgo requiere revision humana o puede aprobarse automaticamente
- Si la operacion completa debe aprobarse o rechazarse

La politica es un archivo de texto (`.rego`) que codifica las reglas de negocio de tu organizacion. Por ejemplo: "cualquier IBAN detectado con confianza > 0.9 requiere revision humana" o "datos medicos siempre son criticos".

### Como ver la politica activa

```bash
# Via API (requiere token valido)
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/mcp/tools/safecontext.policy.get | jq .
```

La respuesta incluye la version actual (`policy_version`) y las reglas activas.

### Como modificar umbrales

Los umbrales de deteccion estan en el archivo `policies/base/safecontext.rego` en el repositorio.

**Ejemplo de cambio de umbral**: Cambiar el umbral de revision humana para EMAIL de 0.75 a 0.85:

```rego
# Antes
requires_review if {
  input.entity_type == "EMAIL"
  input.score >= 0.75
}

# Despues
requires_review if {
  input.entity_type == "EMAIL"
  input.score >= 0.85
}
```

> **Aviso**: Subir el umbral significa que mas hallazgos pasaran automaticamente sin revision humana. Bajarlo significa mas revision manual. Cualquier cambio debe ser aprobado por el CISO o el responsable de cumplimiento antes de desplegarse.

### Como versionar y desplegar una nueva politica

1. Crear una rama en git con el cambio propuesto en `policies/base/safecontext.rego`
2. Incrementar el valor de `policy_version` en el archivo (ej. `1.0.0` → `1.1.0`)
3. Documentar el cambio en el commit message (que se cambio, por que, quien lo aprobo)
4. Crear un Pull Request para revision por pares
5. Tras la aprobacion, mergear y desplegar:

```bash
# En el servidor, tras el merge
docker compose restart opa

# Verificar que la nueva politica se cargo
curl http://localhost:8181/v1/policies | jq '.result[] | select(.id == "safecontext") | .ast.rules[0].head.value'
```

6. Verificar en Grafana que las metricas de recall y revision humana son coherentes con el cambio esperado

---

## 8. Casos de uso frecuentes

### 8.1 "Necesito probar que un documento fue sanitizado antes de llegar a un modelo"

Este es el caso de auditoria de cumplimiento normativo mas comun.

**Proceso**:

1. Obtener el `trace_id` de la operacion en cuestion (del PR comment, de los logs del pipeline, o de la API)
2. Navegar a `/audit` y buscar por `trace_id`
3. Verificar que el campo `operation.status` es `approved`
4. Verificar que el campo `artifacts.original_digest` coincide con el hash del documento original
5. Hacer clic en "Descargar JSON"
6. El JSON descargado, con su firma HMAC, es la evidencia criptograficamente verificable de que:
   - El documento fue procesado por SafeContext
   - Los hallazgos detectados fueron revisados segun la politica activa en ese momento
   - La decision fue tomada por un Reviewer identificado
   - El documento no fue alterado tras el scan

**Para adjuntar en un expediente de auditoria**: incluir el archivo `safecontext_audit_[trace_id].json` y la clave de verificacion obtenida de `GET /v1/audit/verification-key`.

### 8.2 "Un hallazgo fue marcado como falso positivo"

Un falso positivo ocurre cuando Presidio detecta como dato sensible algo que en realidad no lo es (ej. el nombre "Victoria" en una descripcion de una victoria deportiva, interpretado como nombre de persona).

**Flujo correcto**:

1. El Reviewer navega a `/review` y localiza el hallazgo
2. Hace clic en "Ver detalle" para ver el fragmento exacto en contexto
3. Si confirma que es un falso positivo, hace clic en "Rechazar hallazgo"
4. En la justificacion, documenta explicitamente que es un falso positivo:
   - Ejemplo: "Falso positivo: 'victoria' en este contexto es un sustantivo comun (resultado deportivo), no un nombre de persona."
5. La operacion se marca como `rejected` con justificacion documentada

> **Nota importante**: Rechazar un hallazgo como falso positivo no significa que el documento fue aprobado para uso con IA. La operacion queda en estado `rejected`. Si el documento debe procesarse, el equipo debe rescanear el documento (nueva operacion, nuevo trace_id) o el PolicyEditor debe ajustar los umbrales para reducir falsos positivos de esa clase.

**Para reducir falsos positivos sistematicamente**: documentar el patron en el sistema de tickets y contactar al PolicyEditor para ajustar el umbral de confianza de esa entidad en `policies/base/safecontext.rego`.

### 8.3 "Quiero ver todas las operaciones de la ultima semana"

**Desde la UI**:

1. Navegar a `/audit`
2. En el filtro de "Rango de fechas", seleccionar los ultimos 7 dias
3. Opcionalmente filtrar por estado (`approved`, `rejected`, `pending_review`) o por actor
4. La tabla muestra todas las operaciones con sus estados y permite exportar cada una

**Desde PostgreSQL** (para usuarios tecnicos con acceso a la base de datos):

```sql
SELECT
  trace_id,
  created_at,
  status,
  actor_id,
  policy_version,
  (SELECT count(*) FROM findings f WHERE f.operation_id = o.id) as findings_count
FROM operations o
WHERE created_at >= NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;
```

**Desde Prometheus** (metricas agregadas, no datos individuales):

```promql
# Total de scans en los ultimos 7 dias
increase(safecontext_scans_total[7d])

# Desglose por estado
increase(safecontext_scans_total{status="approved"}[7d])
increase(safecontext_scans_total{status="rejected"}[7d])
increase(safecontext_scans_total{status="pending_review"}[7d])
```

### 8.4 "Un pipeline bloqueo y necesito desbloquearlo"

Un pipeline queda bloqueado cuando una operacion esta en estado `pending_review` y el CI/CD espera la decision del Reviewer.

**Proceso para desbloquear**:

1. Localizar el `trace_id` en el comentario del bot de SafeContext en el PR
2. Navegar a `http://[host]:8088/review`
3. Buscar la operacion por `trace_id` o encontrarla en la lista de "Pendientes"
4. Revisar cada hallazgo en detalle
5. Para cada hallazgo, decidir: Aprobar o Rechazar (con justificacion)
6. Una vez que todos los hallazgos tienen decision, la operacion cambia de estado automaticamente
7. El pipeline CI/CD detecta el cambio de estado y:
   - Si la operacion es `approved`: el pipeline continua
   - Si la operacion es `rejected`: el pipeline falla con el mensaje de rechazo

**Tiempo limite**: Por defecto, las operaciones en estado `pending_review` expiran tras 48 horas sin decision. Si expiran, el pipeline falla automaticamente y debe rescanear el documento.

---

## 9. Glosario para usuarios de negocio

| Termino | Definicion en lenguaje de negocio |
|---|---|
| **Hallazgo** | Una deteccion de informacion potencialmente sensible en un documento. Puede ser un nombre, un email, un numero de cuenta bancaria, etc. Cada hallazgo tiene una severidad y una confianza asociadas. |
| **Sanitizacion** | El proceso de reemplazar la informacion sensible en un documento por etiquetas neutrales (ej. sustituir "Juan Garcia" por "[PERSON]"). El documento sanitizado puede enviarse a la IA sin revelar datos reales. |
| **Trace ID** | Un codigo unico (como un numero de serie) que identifica una operacion de scan especifica. Es el identificador que usaras para buscar la evidencia de auditoria de una operacion concreta. |
| **Politica** | El conjunto de reglas que determina como SafeContext evalua cada hallazgo. Define cosas como: "un IBAN siempre es de severidad alta" o "un nombre de persona con confianza > 90% requiere revision humana". |
| **Revision humana** | Cuando SafeContext no puede decidir automaticamente si un hallazgo es aceptable, un Reviewer humano debe evaluarlo y tomar la decision. Este mecanismo garantiza que siempre hay supervision humana en las decisiones sensibles. |
| **Evidencia** | El registro exportable de una operacion de scan, con todos sus hallazgos, decisiones y firmas criptograficas. Es el documento que se presenta ante auditores para demostrar que un proceso fue seguido correctamente. |
| **Audit Trail** | El historial completo e inmutable de todas las operaciones de scan. Cada entrada en el audit trail no puede modificarse ni eliminarse, lo que lo hace apto para presentar ante auditores externos. |
| **Firma HMAC** | Una "huella digital" criptografica del registro de auditoria. Si alguien intentara modificar el registro despues de crearlo, la firma no coincidiria, lo que delataria la manipulacion. Es la garantia de que la evidencia no fue alterada. |
| **Artefacto** | El archivo original y su version sanitizada, almacenados de forma segura e inmutable en SafeContext. El hash (SHA-256) del artefacto original sirve como prueba de que el documento analizado es identico al que se sometio al scan. |
| **SLO** | Service Level Objective — el compromiso de disponibilidad del sistema. SafeContext tiene un SLO del 99.9%, lo que significa que puede estar no disponible como maximo 43 minutos al mes. |
| **Severidad** | La clasificacion del riesgo de un hallazgo: bajo (low), medio (medium), alto (high) o critico (critical). Los hallazgos criticos siempre requieren revision humana y bloquean el pipeline. |
| **Segregacion de funciones** | El principio que impide que la misma persona que submite un documento tambien lo apruebe. Garantiza que siempre hay una segunda opinion en las decisiones de seguridad. |
| **Pipeline** | El proceso automatizado de CI/CD (Continuous Integration / Continuous Deployment) que construye y despliega el software. SafeContext se integra en el pipeline para escanear documentos automaticamente antes de que lleguen a un modelo de IA. |

---

## 10. Módulo de administración (solo rol admin)

Si tienes rol `admin`, en la barra de navegación aparece el enlace **Admin** que te lleva al panel de administración. Este módulo permite gestionar la plataforma completa.

### Páginas del módulo admin

| Página | Ruta | Qué puedes hacer |
|---|---|---|
| **Tenants** | `/admin/tenants` | Ver, crear y desactivar organizaciones (tenants). Cada tenant opera con datos aislados. |
| **Detalle de tenant** | `/admin/tenants/[id]` | Configurar políticas de detección, integración SIEM y retención de datos por tenant. Probar conectividad SIEM. |
| **Waivers** | `/admin/waivers` | Crear excepciones de política (requiere justificación de al menos 20 caracteres) y revocar waivers existentes. También accesible para `policy_editor`. |
| **Retención** | `/admin/retention` | Configurar días de retención, ejecutar purga GDPR manual y consultar certificados de borrado. |

Para detalle técnico de cada flujo administrativo, ver [Manual 07 — Administración y Configuración](./07_ADMIN_CONFIGURACION.md).

---

*Manual de Usuario SafeContext v2.0.0 — 2026-05-25*
*Para soporte operativo, contactar al equipo SRE. Para dudas de cumplimiento, contactar al CISO.*
