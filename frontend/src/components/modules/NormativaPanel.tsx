import { useState } from 'react'
import {
  FileText, Search, ExternalLink, AlertTriangle, Loader2,
  BookOpen, Calendar, ChevronRight
} from 'lucide-react'
import { normativaApi } from '../../api/client'

const FUENTE_CONFIG = {
  cantabria: {
    label: 'BOC Cantabria',
    fn: 'boc' as const,
    color: 'bg-green-100 text-green-700',
    descripcion: 'Boletín Oficial de Cantabria',
  },
  asturias: {
    label: 'BOPA Asturias',
    fn: 'bopa' as const,
    color: 'bg-blue-100 text-blue-700',
    descripcion: 'Boletín Oficial del Principado de Asturias',
  },
  boe: {
    label: 'BOE Estatal',
    fn: 'boe' as const,
    color: 'bg-orange-100 text-orange-700',
    descripcion: 'Boletín Oficial del Estado',
  },
}

const BUSQUEDAS_FRECUENTES = [
  'vivienda turística',
  'licencia obra mayor',
  'planeamiento urbanístico',
  'suelo no urbanizable',
  'protección patrimonio',
  'actividades clasificadas',
  'medio ambiente',
  'ordenanza municipal',
]

type Fuente = keyof typeof FUENTE_CONFIG

interface ResultadoNormativa {
  fuente: string
  query: string
  total: number
  url_busqueda_manual: string
  resultados: Array<{
    titulo: string
    fecha: string | null
    url: string | null
    resumen: string | null
    fuente: string
  }>
}

export function NormativaPanel() {
  const [fuente, setFuente] = useState<Fuente>('cantabria')
  const [q, setQ] = useState('')
  const [fechaDesde, setFechaDesde] = useState('')
  const [respuesta, setRespuesta] = useState<ResultadoNormativa | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<{ mensaje: string; urlManual?: string } | null>(null)
  const [mostrarFiltros, setMostrarFiltros] = useState(false)

  const handleBuscar = async (termino?: string) => {
    const busqueda = termino || q
    if (!busqueda.trim()) return
    if (termino) setQ(termino)
    setLoading(true); setError(null); setRespuesta(null)

    try {
      const config = FUENTE_CONFIG[fuente]
      const fn = normativaApi[config.fn]
      const data = await fn(busqueda, fechaDesde || undefined)
      // La API devuelve {fuente, query, total, resultados, url_busqueda_manual}
      setRespuesta(data as ResultadoNormativa)
    } catch (e: any) {
      // El backend puede devolver detail como objeto con url_busqueda_manual
      const detail = e.response?.data?.detail || {}
      setError({
        mensaje: detail.mensaje || e.message || 'Error al consultar el boletín',
        urlManual: detail.url_busqueda_manual,
      })
    } finally {
      setLoading(false)
    }
  }

  const config = FUENTE_CONFIG[fuente]

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Normativa</h2>
        <p className="text-sm text-gray-500 mt-1">
          Búsqueda en BOC (Cantabria), BOPA (Asturias) y BOE estatal
        </p>
      </div>

      {/* Selector de boletín */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div className="flex gap-2">
          {(Object.entries(FUENTE_CONFIG) as [Fuente, typeof FUENTE_CONFIG[Fuente]][]).map(([key, cfg]) => (
            <button
              key={key}
              onClick={() => { setFuente(key); setRespuesta(null); setError(null) }}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                fuente === key ? 'bg-sky-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {cfg.label}
            </button>
          ))}
        </div>

        {/* Campo de búsqueda */}
        <div className="flex gap-2">
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleBuscar()}
            placeholder={`Buscar en ${config.descripcion}...`}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          <button
            onClick={() => setMostrarFiltros(!mostrarFiltros)}
            className="px-3 py-2 rounded-lg border border-gray-300 text-sm text-gray-600 hover:bg-gray-50"
            title="Filtros"
          >
            <Calendar size={16} />
          </button>
          <button
            onClick={() => handleBuscar()}
            disabled={loading || !q.trim()}
            className="flex items-center gap-2 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white px-5 py-2 rounded-lg text-sm font-medium"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
            {loading ? 'Buscando...' : 'Buscar'}
          </button>
        </div>

        {/* Filtro de fecha */}
        {mostrarFiltros && (
          <div className="flex items-center gap-3 text-sm">
            <label className="text-gray-600 font-medium">Desde:</label>
            <input
              type="date"
              value={fechaDesde}
              onChange={(e) => setFechaDesde(e.target.value)}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
            />
            {fechaDesde && (
              <button onClick={() => setFechaDesde('')} className="text-gray-400 hover:text-gray-600 text-xs">
                Limpiar
              </button>
            )}
          </div>
        )}

        {/* Búsquedas frecuentes */}
        <div>
          <p className="text-xs text-gray-400 mb-2">Búsquedas frecuentes:</p>
          <div className="flex flex-wrap gap-1.5">
            {BUSQUEDAS_FRECUENTES.map((t) => (
              <button
                key={t}
                onClick={() => handleBuscar(t)}
                className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-600 hover:bg-sky-100 hover:text-sky-700 transition-colors"
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 space-y-2">
          <div className="flex items-start gap-2">
            <AlertTriangle size={18} className="text-red-600 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-red-800">{error.mensaje}</p>
              {error.urlManual && (
                <a
                  href={error.urlManual}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-sm text-red-700 underline hover:text-red-900"
                >
                  Buscar manualmente en {config.descripcion}
                  <ExternalLink size={12} />
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center">
          <Loader2 size={28} className="mx-auto mb-3 text-sky-600 animate-spin" />
          <p className="text-sm text-gray-500">Consultando {config.descripcion}...</p>
        </div>
      )}

      {/* Resultados */}
      {respuesta && !loading && (
        <div className="space-y-3">
          {/* Cabecera de resultados */}
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${config.color}`}>
                {config.label}
              </span>
              <span className="text-sm text-gray-600">
                {respuesta.total === 0
                  ? 'Sin resultados'
                  : `${respuesta.total} resultado${respuesta.total !== 1 ? 's' : ''}`}
                {respuesta.query && <> para "<strong>{respuesta.query}</strong>"</>}
              </span>
            </div>
            {respuesta.url_busqueda_manual && (
              <a
                href={respuesta.url_busqueda_manual}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-gray-500 hover:text-sky-600"
              >
                Buscar en {config.descripcion} <ExternalLink size={12} />
              </a>
            )}
          </div>

          {respuesta.total === 0 ? (
            <div className="bg-white rounded-xl border border-gray-200 p-10 text-center">
              <BookOpen size={32} className="mx-auto mb-3 text-gray-300" />
              <p className="text-sm text-gray-500">
                No se encontraron resultados para "{respuesta.query}"
              </p>
              {respuesta.url_busqueda_manual && (
                <a
                  href={respuesta.url_busqueda_manual}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1 text-sm text-sky-600 hover:underline"
                >
                  Probar búsqueda manual <ExternalLink size={12} />
                </a>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden divide-y">
              {respuesta.resultados.map((r, i) => (
                <div key={i} className="p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 leading-snug">
                        {r.titulo}
                      </p>
                      {r.resumen && (
                        <p className="text-xs text-gray-500 mt-1 line-clamp-2">{r.resumen}</p>
                      )}
                      <div className="flex items-center gap-3 mt-2">
                        {r.fecha && (
                          <span className="flex items-center gap-1 text-xs text-gray-400">
                            <Calendar size={11} />
                            {r.fecha}
                          </span>
                        )}
                      </div>
                    </div>
                    {r.url && (
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-shrink-0 flex items-center gap-1 text-xs font-medium text-sky-600 hover:text-sky-800 px-3 py-1.5 rounded-lg border border-sky-200 hover:bg-sky-50"
                      >
                        Ver <ChevronRight size={12} />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
