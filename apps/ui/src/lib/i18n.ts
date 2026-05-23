/**
 * i18n preparation — centralized UI strings.
 *
 * All user-visible strings are collected here so a future i18n library
 * (e.g. next-intl, react-i18next) can replace this module without
 * touching individual components.
 *
 * Usage:
 *   import { t } from '@/lib/i18n'
 *   <p>{t('common.loading')}</p>
 *
 * When adopting a real i18n library:
 *   1. Replace the `t` export with the library's translation function.
 *   2. Move the strings object into locale JSON files (es.json, en.json).
 *   3. Components stay unchanged — they already call `t(key)`.
 */

const strings: Record<string, string> = {
  // ── Common ─────────────────────────────────────────────────────────────
  'common.loading': 'Cargando...',
  'common.error': 'Error',
  'common.retry': 'Intentar de nuevo',
  'common.cancel': 'Cancelar',
  'common.confirm': 'Confirmar',
  'common.save': 'Guardar',
  'common.delete': 'Eliminar',
  'common.back': 'Volver',
  'common.next': 'Siguiente',
  'common.previous': 'Anterior',
  'common.search': 'Buscar',
  'common.noResults': 'Sin resultados',
  'common.signOut': 'Sign out',

  // ── Navigation ─────────────────────────────────────────────────────────
  'nav.dashboard': 'Dashboard',
  'nav.scan': 'Scan',
  'nav.review': 'Review',
  'nav.audit': 'Audit',
  'nav.grafana': 'Grafana',

  // ── Dashboard ──────────────────────────────────────────────────────────
  'dashboard.welcome': 'Bienvenido',
  'dashboard.subtitle': 'SafeContext — Gobierno de documentos para IA',
  'dashboard.systemHealth': 'Estado del sistema',
  'dashboard.refresh': 'Refrescar',
  'dashboard.activity': 'Actividad — últimas 24 h',
  'dashboard.recentActivity': 'Actividad reciente',
  'dashboard.totalScans': 'Total scans',
  'dashboard.approved': 'Aprobados',
  'dashboard.pendingReview': 'Pendientes de revisión',
  'dashboard.rejected': 'Rechazados',
  'dashboard.needsAttention': 'Requieren atención',
  'dashboard.comingSoon': 'Disponible próximamente',
  'dashboard.noHistory': 'Sin historial disponible',
  'dashboard.noOps': 'Todavía no hay operaciones registradas.',
  'dashboard.quickLinks': 'Accesos rápidos',

  // ── Scan ───────────────────────────────────────────────────────────────
  'scan.title': 'Escanear documento',
  'scan.placeholder': 'Pega el contenido del documento aquí...',
  'scan.button': 'Escanear',
  'scan.scanning': 'Escaneando...',
  'scan.success': 'Escaneo completado',
  'scan.emptyDoc': 'El documento no puede estar vacío',
  'scan.timeout': 'Scan timeout',

  // ── Review ─────────────────────────────────────────────────────────────
  'review.title': 'Revisiones pendientes',
  'review.approve': 'Aprobar',
  'review.reject': 'Rechazar',
  'review.justification': 'Justificación',
  'review.justificationPlaceholder': 'Describe el motivo de tu decisión...',
  'review.minChars': 'Mínimo {0} caracteres',
  'review.processing': 'Procesando...',

  // ── Audit ──────────────────────────────────────────────────────────────
  'audit.title': 'Audit Trail',
  'audit.searchByTrace': 'Buscar por Trace ID',
  'audit.export': 'Exportar',
  'audit.notFound': 'Trace ID no encontrado',

  // ── Errors ─────────────────────────────────────────────────────────────
  'error.unexpected': 'Algo salió mal',
  'error.unexpected.description': 'Ocurrió un error inesperado. Puedes intentar nuevamente o volver al inicio.',
  'error.backToDashboard': 'Ir al inicio',
  'error.apiDown': 'No se puede conectar con la API. Comprueba que el backend está activo.',
}

/**
 * Look up a UI string by key.  Returns the key itself if not found,
 * so missing translations are visible during development.
 */
export function t(key: string, ...args: (string | number)[]): string {
  let value = strings[key] ?? key
  // Simple positional placeholder replacement: {0}, {1}, etc.
  args.forEach((arg, i) => {
    value = value.replace(`{${i}}`, String(arg))
  })
  return value
}
