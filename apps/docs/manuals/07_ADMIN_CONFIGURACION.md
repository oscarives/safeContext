# SafeContext — Manual de Administracion y Configuracion

**Version**: 1.0.0 | **Fecha**: 2026-05-24 | **Audiencia**: Administradores de plataforma, SRE, DevOps

---

## Tabla de Contenidos

1. [Requisitos previos](#1-requisitos-previos)
2. [Acceso al panel de administracion](#2-acceso-al-panel-de-administracion)
3. [Gestion de tenants](#3-gestion-de-tenants)
4. [Configuracion de politicas por tenant](#4-configuracion-de-politicas-por-tenant)
5. [Configuracion SIEM](#5-configuracion-siem)
6. [Gestion de waivers](#6-gestion-de-waivers)
7. [Retencion GDPR y certificados de eliminacion](#7-retencion-gdpr-y-certificados-de-eliminacion)
8. [Referencia de roles y permisos](#8-referencia-de-roles-y-permisos)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Requisitos previos

### Roles necesarios

Para acceder al panel de administracion necesitas uno de estos roles asignados en Keycloak:

| Rol | Alcance |
|---|---|
| `platform_admin` | Acceso completo: crear/editar/desactivar tenants, purgar datos, gestionar waivers |
| `admin` | Acceso completo al panel de administracion |

Los roles `policy_editor` y `reviewer` tienen acceso parcial (ver seccion 8).

### Acceso al sistema

1. Iniciar sesion en SafeContext con tus credenciales corporativas (SSO via Keycloak)
2. Verificar que el enlace **Admin** aparece en la barra de navegacion superior
3. Si no aparece, contacta al administrador de Keycloak para solicitar el rol necesario

---

## 2. Acceso al panel de administracion

### Navegacion

1. Haz clic en **Admin** en la barra de navegacion superior (solo visible para roles `admin` o `platform_admin`)
2. Se abre el panel con un sidebar lateral con tres secciones:
   - **Tenants** — Gestion de organizaciones
   - **Waivers** — Excepciones a politicas de deteccion
   - **Retention** — Configuracion de retencion GDPR

### Pantalla de acceso denegado

Si tu usuario no tiene el rol requerido, veras un mensaje de error con boton para volver al dashboard. Solicita el rol apropiado al administrador de Keycloak.

---

## 3. Gestion de tenants

### Listar tenants

La pagina principal de Tenants muestra una tabla con todas las organizaciones configuradas:

| Columna | Descripcion |
|---|---|
| **Name** | Nombre del tenant (enlace a detalle) |
| **Slug** | Identificador unico URL-safe |
| **Plan** | `free`, `starter` o `enterprise` |
| **Status** | `Active` o `Inactive` |
| **Scans/Day** | Limite diario de escaneos (o "Unlimited") |
| **Retention** | Dias de retencion de datos |

### Crear un tenant

1. Clic en **Create Tenant** (esquina superior derecha)
2. Completar el formulario:
   - **Name**: Nombre descriptivo (ej: "Acme Corp")
   - **Slug**: Identificador unico, solo minusculas y guiones (ej: "acme-corp"). Formato: `^[a-z0-9][a-z0-9-]*[a-z0-9]$`
   - **Plan**: Seleccionar `free`, `starter` o `enterprise`
   - **Contact Email**: Email del administrador del tenant (opcional)
   - **Max Scans/Day**: Limite diario de escaneos. Dejar vacio para ilimitado
3. Clic en **Create**
4. El tenant aparecera en la tabla con estado "Active"

### Editar un tenant

1. Clic en el nombre del tenant en la tabla
2. Se abre la pagina de detalle con 3 tabs: **General**, **Policies**, **SIEM**
3. En la tab **General** puedes modificar:
   - Nombre y slug
   - Plan (`free` / `starter` / `enterprise`)
   - Email de contacto
   - Limite de escaneos diarios
   - Dias de retencion
4. Clic en **Save Changes** para guardar

### Desactivar un tenant

1. En la tabla de tenants, clic en **Deactivate** en la fila del tenant
2. Aparece un dialogo de confirmacion
3. Confirmar la desactivacion
4. El tenant pasa a estado "Inactive". Los datos se conservan pero el tenant no puede realizar operaciones

> **Nota**: La desactivacion no elimina datos. Para eliminar datos, usa la funcionalidad de purga GDPR (seccion 7).

---

## 4. Configuracion de politicas por tenant

Cada tenant puede personalizar las politicas de deteccion de datos sensibles. Estas configuraciones modifican el comportamiento del motor OPA (Open Policy Agent) para ese tenant especifico.

### Acceder a la configuracion

1. Ir a **Tenants** > clic en el nombre del tenant
2. Seleccionar la tab **Policies**

### Umbrales de confianza (Confidence Overrides)

Permiten ajustar la sensibilidad de deteccion por tipo de entidad.

| Campo | Descripcion | Rango |
|---|---|---|
| Entity Type | Tipo de dato sensible (ej: `API_KEY`, `EMAIL`, `IP_ADDRESS`) | Selector |
| Confidence | Umbral minimo de confianza para considerar un hallazgo | 0.00 a 1.00 |

**Valores default OPA** (si no se configura):

| Tipo | Umbral default |
|---|---|
| API_KEY | 0.70 |
| JWT | 0.60 |
| CONNECTION_STRING | 0.65 |
| EMAIL | 0.80 |
| Otros | 0.50 |

**Procedimiento**:
1. Seleccionar el tipo de entidad del dropdown
2. Ajustar el slider al valor deseado (0.00 = detectar todo, 1.00 = solo alta confianza)
3. Clic en **Add** para agregar la regla
4. Repetir para otros tipos
5. Clic en **Save** para aplicar

### Severidades personalizadas (Severity Overrides)

Permiten reclasificar la severidad de un tipo de hallazgo.

| Severidad | Significado |
|---|---|
| `low` | Informativo, no requiere accion |
| `medium` | Revisar en proxima iteracion |
| `high` | Requiere atencion inmediata |
| `critical` | Bloquea la operacion, requiere revision humana |

**Procedimiento**:
1. Seleccionar el tipo de entidad
2. Seleccionar la severidad deseada del dropdown
3. Clic en **Add**
4. Clic en **Save**

### Tipos de entidad bloqueados

Permiten bloquear completamente ciertos tipos de datos sensibles para un tenant.

**Tipos disponibles**: `API_KEY`, `JWT`, `CONNECTION_STRING`, `PRIVATE_KEY`, `EMAIL`, `IP_ADDRESS`, `SSN`, `CREDIT_CARD`, `PASSWORD`, `PHONE_NUMBER`

**Procedimiento**:
1. Marcar la casilla junto a cada tipo que deseas bloquear
2. Los documentos que contengan estos tipos seran rechazados automaticamente
3. Clic en **Save**

---

## 5. Configuracion SIEM

SafeContext puede enviar eventos de seguridad a un sistema SIEM (Security Information and Event Management) via webhook HTTP o syslog.

### Acceder a la configuracion

1. Ir a **Tenants** > clic en el nombre del tenant
2. Seleccionar la tab **SIEM**

### Habilitar SIEM

1. Activar el toggle **Enable SIEM**
2. Seleccionar el formato de eventos:
   - **CEF** (Common Event Format) — compatible con ArcSight, QRadar
   - **LEEF** (Log Event Extended Format) — compatible con QRadar
   - **JSON** — formato generico, compatible con Splunk, ELK

### Configurar Webhook

Para enviar eventos via HTTP POST:

1. Ingresar la **Webhook URL** (ej: `https://siem.empresa.com/api/events`)
2. Ingresar el **Webhook Token** (cabecera `Authorization: Bearer <token>`)
3. Clic en **Save**

### Configurar Syslog

Para enviar eventos via syslog:

1. Ingresar el **Syslog Host** (IP o hostname del servidor syslog)
2. Ingresar el **Syslog Port** (default: 514, rango: 1-65535)
3. Seleccionar el **Protocol**: UDP o TCP
4. Clic en **Save**

### Probar la conexion

1. Configurar al menos un destino (webhook o syslog)
2. Clic en **Test Connection**
3. El sistema enviara un evento de prueba y mostrara el resultado:
   - **Webhook**: OK / Error (con detalle)
   - **Syslog**: OK / Error (con detalle)

> **Nota**: Se puede configurar webhook y syslog simultaneamente. Los eventos se envian a ambos destinos.

---

## 6. Gestion de waivers

Los waivers son excepciones a las politicas de deteccion. Permiten marcar ciertos patrones como "falsos positivos conocidos" para que no generen hallazgos en futuros escaneos.

### Roles necesarios

| Accion | Roles permitidos |
|---|---|
| Ver waivers | Cualquier rol admin |
| Crear waiver | `policy_editor`, `admin`, `platform_admin` |
| Revocar waiver | `policy_editor`, `admin`, `platform_admin` |

### Listar waivers

La tabla muestra todos los waivers con las columnas:

| Columna | Descripcion |
|---|---|
| **Rule ID** | Identificador de la regla de deteccion (ej: `regex_connection_string`) |
| **Entity Pattern** | Expresion regular que coincide con el patron a ignorar |
| **Justification** | Razon documentada para la excepcion |
| **Status** | `active` o `revoked` |
| **Expires** | Fecha de expiracion (o "Never") |
| **Created** | Fecha de creacion |

### Crear un waiver

1. Clic en **Create Waiver**
2. Completar el formulario:
   - **Rule ID**: Identificador de la regla (ej: `regex_connection_string`, `regex_api_key`)
   - **Entity Pattern (regex)**: Expresion regular que coincide con los valores a ignorar (ej: `localhost.*testdb`). Se valida en tiempo real
   - **Justification**: Explicacion detallada de por que es un falso positivo. Minimo 20 caracteres
   - **Expires At**: Fecha de expiracion opcional. Si se omite, el waiver no expira
3. Clic en **Create**

**Ejemplo de uso**: Un equipo usa la cadena de conexion `mongodb://localhost:27017/testdb` en su documentacion interna. Esta cadena es detectada como `CONNECTION_STRING` pero no es un secreto real. Se crea un waiver con pattern `localhost.*testdb` y justificacion que explica el contexto.

### Revocar un waiver

1. En la tabla, clic en **Revoke** en la fila del waiver activo
2. Confirmar la revocacion en el dialogo
3. El waiver pasa a estado "revoked"
4. Los futuros escaneos volveran a detectar los patrones que cubria el waiver

> **Importante**: Revocar un waiver no retroactivamente marca hallazgos en operaciones pasadas. Solo afecta escaneos futuros.

---

## 7. Retencion GDPR y certificados de eliminacion

SafeContext cumple con el principio de minimizacion de datos del GDPR. Los administradores pueden configurar periodos de retencion y ejecutar purgas manuales de datos expirados.

### Configurar periodo de retencion

1. Ir a la seccion **Retention** en el sidebar
2. Seleccionar el tenant en el dropdown superior
3. Ingresar el numero de dias de retencion (1-3650)
4. Clic en **Save**
5. Las operaciones mas antiguas que el periodo configurado seran elegibles para purga

### Ejecutar purga manual

1. En la seccion **Manual Purge**, clic en **Execute Purge**
2. Aparece un dialogo de confirmacion con el numero de dias configurado
3. Confirmar la purga

**Resultado de la purga**:

| Dato | Descripcion |
|---|---|
| Operations deleted | Numero de operaciones eliminadas |
| Findings deleted | Numero de hallazgos eliminados |
| Redactions deleted | Numero de redacciones eliminadas |
| Artifacts deleted | Numero de artefactos eliminados |
| Certificate ID | Identificador del certificado de eliminacion generado |
| Certificate stored in WORM | Si el certificado fue almacenado en almacenamiento inmutable |

> **Advertencia**: La purga es **irreversible**. Los datos eliminados no pueden recuperarse. El certificado de eliminacion firmado es la unica evidencia de que existieron.

### Certificados de eliminacion

Cada purga genera un certificado de eliminacion firmado que se almacena en WORM (Write Once Read Many) storage. Estos certificados son prueba auditable de que los datos fueron eliminados conforme al GDPR.

**Ver certificados**:

1. En la seccion **Deletion Certificates**, se muestra la lista de certificados
2. Cada certificado muestra: ID, fecha, tamano
3. Clic en **View** para ver el detalle completo en formato JSON
4. El JSON incluye: fecha de purga, tenant, conteo de registros eliminados, firma criptografica

---

## 8. Referencia de roles y permisos

### Matriz de permisos del panel de administracion

| Accion | `platform_admin` | `admin` | `policy_editor` | `reviewer` | `viewer` |
|---|---|---|---|---|---|
| Acceder al panel admin | Si | Si | No | No | No |
| Crear tenant | Si | No | No | No | No |
| Editar tenant | Si | Si | No | No | No |
| Desactivar tenant | Si | Si | No | No | No |
| Configurar politicas | Si | Si | No | No | No |
| Configurar SIEM | Si | Si | No | No | No |
| Crear waiver | Si | Si | Si | No | No |
| Revocar waiver | Si | Si | Si | No | No |
| Ver waivers | Si | Si | Si | No | No |
| Configurar retencion | Si | Si | No | No | No |
| Ejecutar purga | Si | Si | No | No | No |
| Ver certificados | Si | Si | No | Si | No |

### Asignar roles en Keycloak

1. Acceder a la consola de administracion de Keycloak
2. Ir a **Users** > seleccionar usuario
3. Ir a la tab **Role Mappings**
4. Asignar el rol de realm correspondiente (`platform_admin`, `admin`, `policy_editor`, `reviewer`, `viewer`)

---

## 9. Troubleshooting

### "Access Denied" al acceder al panel admin

**Causa**: Tu usuario no tiene el rol `admin` o `platform_admin` en Keycloak.

**Solucion**: Solicitar al administrador de Keycloak que asigne el rol correspondiente.

### Los cambios de politica no se aplican

**Causa**: Las politicas OPA se cachean brevemente.

**Solucion**: Los cambios se aplican en el siguiente escaneo. Si persiste, verificar que el guardado fue exitoso (toast verde de confirmacion).

### El test de SIEM falla

**Posibles causas**:
- **Webhook**: URL incorrecta, token invalido, servidor destino caido, firewall bloqueando
- **Syslog**: Host/puerto incorrectos, protocolo incorrecto (UDP vs TCP), firewall bloqueando

**Solucion**: Verificar conectividad de red al destino. Revisar logs del servidor SIEM para errores de recepcion.

### La purga no elimina datos

**Causa**: No hay operaciones mas antiguas que el periodo de retencion configurado.

**Solucion**: Verificar el periodo de retencion. Si es correcto, no hay datos elegibles para purga (comportamiento normal).

### El certificado de eliminacion no se almacena en WORM

**Causa**: MinIO Object Lock no esta habilitado o configurado correctamente.

**Solucion**: Verificar la configuracion de MinIO:
- Object Lock debe estar habilitado en el bucket `safecontext-worm`
- El bucket debe tener politica de retencion COMPLIANCE configurada
- Verificar credenciales de acceso a MinIO en la configuracion del API

---

*Ultima actualizacion: 2026-05-24 | Version 1.0.0*
