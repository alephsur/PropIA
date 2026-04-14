import { useState, useEffect } from 'react'
import { Map, ChevronDown, ChevronUp, Search, BookOpen, AlertTriangle, CheckCircle, Info, Loader2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { urbanismoApi } from '../../api/client'
import { useAppStore } from '../../stores/appStore'

interface ConsultaTipo {
  titulo: string
  consulta: string
}

interface CategoriaConsultas {
  categoria: string
  consultas: ConsultaTipo[]
}

interface MunicipioIndexado {
  municipio: string
  provincia: string
  ccaa: string
  total_chunks: number
  ultimo_indexado: string | null
}

const CONFIANZA_STYLES = {
  alta: { bg: 'bg-green-50 border-green-200', text: 'text-green-700', icon: CheckCircle, label: 'Confianza alta' },
  media: { bg: 'bg-yellow-50 border-yellow-200', text: 'text-yellow-700', icon: AlertTriangle, label: 'Confianza media' },
  baja: { bg: 'bg-red-50 border-red-200', text: 'text-red-700', icon: AlertTriangle, label: 'Confianza baja' },
}

export function UrbanismoPanel() {
  const { municipioUrbanismo, provinciaUrbanismo, setUrbanismoTarget } = useAppStore()
  const [consulta, setConsulta] = useState('')
  const [resultado, setResultado] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [consultasAbiertas, setConsultasAbiertas] = useState<Set<string>>(new Set())

  const { data: consultasTipo } = useQuery<CategoriaConsultas[]>({
    queryKey: ['consultas-tipo'],
    queryFn: urbanismoApi.consultasTipo,
  })

  const { data: municipios } = useQuery<MunicipioIndexado[]>({
    queryKey: ['municipios-indexados'],
    queryFn: () => urbanismoApi.municipiosIndexados(),
  })

  // Si hay municipios indexados y no hay uno seleccionado, seleccionar el primero
  useEffect(() => {
    if (municipios && municipios.length > 0 && !municipioUrbanismo) {
      setUrbanismoTarget(municipios[0].municipio, municipios[0].provincia)
    }
  }, [municipios, municipioUrbanismo, setUrbanismoTarget])

  const handleConsulta = async (consultaTexto?: string) => {
    const texto = consultaTexto || consulta
    if (!municipioUrbanismo) { setError('Selecciona un municipio'); return }
    if (!texto.trim()) { setError('Escribe o selecciona una consulta'); return }
    setError(null); setLoading(true); setResultado(null)
    try {
      const data = await urbanismoApi.informe({
        provincia: provinciaUrbanismo,
        municipio: municipioUrbanismo,
        consulta: texto,
      })
      setResultado(data)
      if (!consultaTexto) setConsulta('')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const toggleCategoria = (cat: string) => {
    setConsultasAbiertas((prev) => {
      const next = new Set(prev)
      next.has(cat) ? next.delete(cat) : next.add(cat)
      return next
    })
  }

  const usarConsultaPredefinida = (c: ConsultaTipo) => {
    setConsulta(c.consulta)
    handleConsulta(c.consulta)
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Map className="text-sky-600" size={24} />
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Consulta Urbanistica</h2>
          <p className="text-sm text-gray-500">Consulta el PGOU de municipios con documentos indexados</p>
        </div>
      </div>

      {/* Selector de municipio */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Municipio indexado</label>
            {municipios && municipios.length > 0 ? (
              <select
                value={`${municipioUrbanismo}|${provinciaUrbanismo}`}
                onChange={(e) => {
                  const [m, p] = e.target.value.split('|')
                  setUrbanismoTarget(m, p)
                }}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              >
                {municipios.map((m) => (
                  <option key={`${m.municipio}|${m.provincia}`} value={`${m.municipio}|${m.provincia}`}>
                    {m.municipio} ({m.provincia}) - {m.total_chunks} fragmentos
                  </option>
                ))}
              </select>
            ) : (
              <p className="text-sm text-gray-400 py-2">
                No hay municipios indexados. Usa la Biblioteca para descargar e indexar documentos PGOU.
              </p>
            )}
          </div>
          <div className="flex items-end">
            {municipios && municipios.length > 0 && (
              <div className="text-xs text-gray-400">
                {municipios.find(
                  (m) => m.municipio === municipioUrbanismo && m.provincia === provinciaUrbanismo
                )?.ultimo_indexado
                  ? `Indexado: ${new Date(
                      municipios.find(
                        (m) => m.municipio === municipioUrbanismo && m.provincia === provinciaUrbanismo
                      )!.ultimo_indexado!
                    ).toLocaleDateString('es-ES')}`
                  : ''}
              </div>
            )}
          </div>
        </div>

        {/* Consulta libre */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Consulta</label>
          <div className="flex gap-2">
            <textarea
              value={consulta}
              onChange={(e) => setConsulta(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleConsulta() }
              }}
              placeholder="Escribe tu consulta o usa las consultas predefinidas de abajo..."
              rows={2}
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
            <button
              onClick={() => handleConsulta()}
              disabled={loading || !municipioUrbanismo}
              className="flex items-center gap-2 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white px-5 py-2 rounded-lg text-sm font-medium self-end"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
              {loading ? 'Consultando...' : 'Consultar'}
            </button>
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>
        )}
      </div>

      {/* Consultas predefinidas */}
      {consultasTipo && consultasTipo.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b">
            <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
              <BookOpen size={16} />
              Consultas predefinidas
            </div>
          </div>
          <div className="divide-y">
            {consultasTipo.map((cat) => (
              <div key={cat.categoria}>
                <button
                  onClick={() => toggleCategoria(cat.categoria)}
                  className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
                >
                  {cat.categoria}
                  {consultasAbiertas.has(cat.categoria) ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                {consultasAbiertas.has(cat.categoria) && (
                  <div className="px-4 pb-3 grid grid-cols-2 gap-2">
                    {cat.consultas.map((c) => (
                      <button
                        key={c.titulo}
                        onClick={() => usarConsultaPredefinida(c)}
                        disabled={loading || !municipioUrbanismo}
                        className="text-left px-3 py-2 rounded-lg border border-gray-200 text-sm text-gray-700 hover:bg-sky-50 hover:border-sky-300 disabled:opacity-50 transition-colors"
                      >
                        {c.titulo}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <Loader2 size={32} className="mx-auto mb-3 text-sky-600 animate-spin" />
          <p className="text-sm text-gray-500">Buscando en los documentos del PGOU y analizando...</p>
        </div>
      )}

      {/* Resultado */}
      {resultado && !loading && <ResultadoPGOU resultado={resultado} />}
    </div>
  )
}

function ResultadoPGOU({ resultado }: { resultado: any }) {
  const confianza = resultado.confianza || 'baja'
  const estilo = CONFIANZA_STYLES[confianza as keyof typeof CONFIANZA_STYLES] || CONFIANZA_STYLES.baja
  const IconoConfianza = estilo.icon

  const datosEncontrados = resultado.datos_encontrados || {}
  const hayDatos = Object.keys(datosEncontrados).length > 0
  const fragmentos = resultado.fragmentos_clave || []
  const articulos = resultado.articulos_referencia || []
  const nota = resultado.nota

  // Campos urbanisticos (solo mostrar si tienen valor)
  const camposUrbanisticos = [
    { label: 'Clasificacion suelo', value: resultado.clasificacion_suelo },
    { label: 'Zonificacion', value: resultado.zonificacion },
    { label: 'Uso global', value: resultado.uso_global },
    { label: 'Edificabilidad', value: resultado.edificabilidad },
    { label: 'Altura maxima', value: resultado.altura_maxima },
    { label: 'Retranqueos', value: resultado.retranqueos },
    { label: 'Ocupacion maxima', value: resultado.ocupacion_maxima },
    { label: 'Plan vigente', value: resultado.plan_vigente },
  ].filter((c) => c.value && c.value !== 'null')

  const usosPermitidos = (resultado.usos_permitidos || []).filter(Boolean)
  const usosProhibidos = (resultado.usos_prohibidos || []).filter(Boolean)

  return (
    <div className="space-y-4">
      {/* Confianza + Respuesta directa */}
      <div className={`rounded-xl border p-5 ${estilo.bg}`}>
        <div className="flex items-center gap-2 mb-3">
          <IconoConfianza size={18} className={estilo.text} />
          <span className={`text-sm font-medium ${estilo.text}`}>{estilo.label}</span>
        </div>
        <p className="text-gray-900 leading-relaxed">
          {resultado.respuesta_directa || 'Sin respuesta directa del modelo.'}
        </p>
      </div>

      {/* Nota / advertencia */}
      {nota && (
        <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
          <Info size={16} className="text-amber-600 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-amber-800">{nota}</p>
        </div>
      )}

      {/* Datos encontrados (tabla) */}
      {hayDatos && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b text-sm font-medium text-gray-700">
            Datos encontrados en el PGOU
          </div>
          <table className="w-full text-sm">
            <tbody className="divide-y">
              {Object.entries(datosEncontrados).map(([clave, valor]) => (
                <tr key={clave} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 text-gray-600 font-medium w-1/3">{clave}</td>
                  <td className="px-4 py-2.5 text-gray-900">{String(valor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Campos urbanisticos */}
      {camposUrbanisticos.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b text-sm font-medium text-gray-700">
            Parametros urbanisticos
          </div>
          <div className="grid grid-cols-2 divide-x divide-y">
            {camposUrbanisticos.map((campo) => (
              <div key={campo.label} className="px-4 py-3">
                <p className="text-xs text-gray-500 mb-1">{campo.label}</p>
                <p className="text-sm text-gray-900 font-medium">{campo.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Usos permitidos / prohibidos */}
      {(usosPermitidos.length > 0 || usosProhibidos.length > 0) && (
        <div className="grid grid-cols-2 gap-4">
          {usosPermitidos.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-sm font-medium text-green-700 mb-2">Usos permitidos</p>
              <ul className="space-y-1">
                {usosPermitidos.map((u: string, i: number) => (
                  <li key={i} className="text-sm text-gray-700 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0" />
                    {u}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {usosProhibidos.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4">
              <p className="text-sm font-medium text-red-700 mb-2">Usos prohibidos</p>
              <ul className="space-y-1">
                {usosProhibidos.map((u: string, i: number) => (
                  <li key={i} className="text-sm text-gray-700 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
                    {u}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Fragmentos clave (citas literales) */}
      {fragmentos.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b text-sm font-medium text-gray-700">
            Fragmentos del PGOU citados
          </div>
          <div className="p-4 space-y-3">
            {fragmentos.map((frag: string, i: number) => (
              <blockquote key={i} className="border-l-3 border-sky-300 pl-4 py-1 text-sm text-gray-700 italic bg-sky-50/50 rounded-r-lg pr-3">
                "{frag}"
              </blockquote>
            ))}
          </div>
        </div>
      )}

      {/* Articulos referencia */}
      {articulos.length > 0 && (
        <div className="flex flex-wrap gap-2 px-1">
          {articulos.map((art: string, i: number) => (
            <span key={i} className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
              {art}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
