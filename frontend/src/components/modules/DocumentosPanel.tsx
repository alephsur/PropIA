import { useState, useRef } from 'react'
import {
  Upload, FileSearch, FileText, AlertTriangle, Info,
  CheckCircle, XCircle, User, Home, Calendar, Loader2, X
} from 'lucide-react'
import { documentosApi } from '../../api/client'

const TIPO_LABELS: Record<string, string> = {
  escritura: 'Escritura notarial',
  cedula_habitabilidad: 'Cedula de habitabilidad',
  licencia: 'Licencia de obra / actividad',
  nota_simple: 'Nota simple registral',
  plano: 'Plano',
  contrato: 'Contrato',
  otro: 'Otro documento',
}

const TIPO_COLORS: Record<string, string> = {
  escritura: 'bg-purple-100 text-purple-700',
  cedula_habitabilidad: 'bg-green-100 text-green-700',
  licencia: 'bg-blue-100 text-blue-700',
  nota_simple: 'bg-indigo-100 text-indigo-700',
  plano: 'bg-gray-100 text-gray-700',
  contrato: 'bg-orange-100 text-orange-700',
  otro: 'bg-gray-100 text-gray-600',
}

const ALERTA_STYLES: Record<string, { bg: string; text: string; icon: any }> = {
  danger: { bg: 'bg-red-50 border-red-200', text: 'text-red-800', icon: XCircle },
  warning: { bg: 'bg-amber-50 border-amber-200', text: 'text-amber-800', icon: AlertTriangle },
  info: { bg: 'bg-blue-50 border-blue-200', text: 'text-blue-800', icon: Info },
}

const CARGA_COLORS: Record<string, string> = {
  hipoteca: 'bg-red-50 border-red-200 text-red-800',
  embargo: 'bg-orange-50 border-orange-200 text-orange-800',
  servidumbre: 'bg-yellow-50 border-yellow-200 text-yellow-800',
  anotacion: 'bg-blue-50 border-blue-200 text-blue-800',
  otro: 'bg-gray-50 border-gray-200 text-gray-700',
}

const CONSULTAS_RAPIDAS = [
  'Identificar cargas e hipotecas sobre la finca',
  'Extraer datos de los titulares y porcentajes de propiedad',
  'Verificar referencias catastrales y registrales',
  'Comprobar si la cedula de habitabilidad esta vigente',
  'Identificar condiciones especiales o limitaciones',
]

const ACCEPT_TYPES = '.pdf,image/jpeg,image/png,image/webp'

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function DocumentosPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [consulta, setConsulta] = useState('')
  const [resultado, setResultado] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File | null) => {
    setFile(f)
    setResultado(null)
    setError(null)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) handleFile(f)
  }

  const handleAnalizar = async () => {
    if (!file) { setError('Selecciona un documento'); return }
    const fd = new FormData()
    fd.append('documento', file)
    if (consulta.trim()) fd.append('consulta', consulta.trim())
    setLoading(true); setError(null); setResultado(null)
    try {
      const data = await documentosApi.analizar(fd)
      setResultado(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Analisis de Documentos</h2>
        <p className="text-sm text-gray-500 mt-1">
          Extrae informacion de escrituras, notas simples, cedulas y mas
        </p>
      </div>

      {/* Upload */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => !file && inputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors
            ${file ? 'border-sky-300 bg-sky-50' : dragging ? 'border-sky-400 bg-sky-50' : 'border-gray-300 hover:border-sky-400 cursor-pointer'}`}
        >
          {file ? (
            <div className="flex items-center justify-center gap-3">
              <FileText size={24} className="text-sky-600 flex-shrink-0" />
              <div className="text-left">
                <p className="text-sm font-medium text-gray-900">{file.name}</p>
                <p className="text-xs text-gray-500">{formatBytes(file.size)}</p>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); handleFile(null) }}
                className="ml-2 p-1 rounded hover:bg-sky-100"
              >
                <X size={16} className="text-gray-400 hover:text-red-500" />
              </button>
            </div>
          ) : (
            <>
              <Upload className="mx-auto mb-2 text-gray-400" size={32} />
              <p className="text-sm text-gray-600 font-medium">
                Arrastra el documento aqui o haz clic para seleccionar
              </p>
              <p className="text-xs text-gray-400 mt-1">
                PDF, JPG, PNG, WEBP — maximo 100 MB
              </p>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT_TYPES}
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0] || null)}
          />
        </div>

        {/* Consulta especifica */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Consulta especifica <span className="text-gray-400 font-normal">(opcional)</span>
          </label>
          <textarea
            value={consulta}
            onChange={(e) => setConsulta(e.target.value)}
            placeholder="¿Hay cargas sobre la finca? ¿Quien es el titular? ..."
            rows={2}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
          />
          {/* Consultas rapidas */}
          <div className="flex flex-wrap gap-1.5 mt-2">
            {CONSULTAS_RAPIDAS.map((c) => (
              <button
                key={c}
                onClick={() => setConsulta(c)}
                className="text-xs px-2.5 py-1 rounded-full bg-gray-100 text-gray-600 hover:bg-sky-100 hover:text-sky-700 transition-colors"
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}

        <button
          onClick={handleAnalizar}
          disabled={loading || !file}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-sm font-medium"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <FileSearch size={16} />}
          {loading ? 'Analizando documento...' : 'Analizar documento'}
        </button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center">
          <Loader2 size={32} className="mx-auto mb-3 text-sky-600 animate-spin" />
          <p className="text-sm text-gray-500">
            El modelo esta leyendo el documento...
          </p>
          <p className="text-xs text-gray-400 mt-1">
            Esto puede tardar hasta 2 minutos segun el tamano del documento
          </p>
        </div>
      )}

      {/* Resultado */}
      {resultado && !loading && <ResultadoDocumento resultado={resultado} />}
    </div>
  )
}

function ResultadoDocumento({ resultado }: { resultado: any }) {
  const tipo = resultado.tipo_documento || 'otro'
  const alertas: any[] = resultado.alertas || []
  const datosDict: Record<string, string> = resultado.datos_principales || {}
  const superficies = resultado.superficies || {}
  const titulares: any[] = resultado.titulares || []
  const cargas: any[] = resultado.cargas || []
  const refs_catastrales: string[] = resultado.referencias_catastrales || []
  const refs_registrales: any[] = resultado.referencias_registrales || []
  const condiciones: string[] = resultado.condiciones_relevantes || []
  const fechas = resultado.fechas_relevantes || {}
  const resumen: string = resultado.resumen || ''

  const hayDatos = Object.keys(datosDict).length > 0
  const haySuperficies = Object.values(superficies).some(Boolean)
  const hayFechas = Object.values(fechas).some(Boolean)

  return (
    <div className="space-y-4">
      {/* Tipo + Resumen */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1 rounded-full text-xs font-semibold ${TIPO_COLORS[tipo] || TIPO_COLORS.otro}`}>
            {TIPO_LABELS[tipo] || tipo}
          </span>
        </div>
        {resumen && (
          <p className="text-gray-800 leading-relaxed">{resumen}</p>
        )}
      </div>

      {/* Alertas */}
      {alertas.length > 0 && (
        <div className="space-y-2">
          {alertas.map((a, i) => {
            const nivel = a.nivel || 'info'
            const estilo = ALERTA_STYLES[nivel] || ALERTA_STYLES.info
            const Icono = estilo.icon
            return (
              <div key={i} className={`flex items-start gap-2.5 border rounded-lg px-4 py-3 ${estilo.bg}`}>
                <Icono size={16} className={`mt-0.5 flex-shrink-0 ${estilo.text}`} />
                <p className={`text-sm ${estilo.text}`}>{a.texto}</p>
              </div>
            )
          })}
        </div>
      )}

      {/* Cargas — seccion mas importante para un agente */}
      {cargas.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-red-50 border-b border-red-100 flex items-center gap-2">
            <AlertTriangle size={16} className="text-red-600" />
            <span className="text-sm font-semibold text-red-700">
              Cargas y gravamenes ({cargas.length})
            </span>
          </div>
          <div className="p-4 space-y-3">
            {cargas.map((c, i) => (
              <div key={i} className={`border rounded-lg p-3 ${CARGA_COLORS[c.tipo] || CARGA_COLORS.otro}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold uppercase tracking-wide">
                    {c.tipo}
                  </span>
                  {c.importe_eur && (
                    <span className="text-sm font-semibold">
                      {Number(c.importe_eur).toLocaleString('es-ES')} EUR
                    </span>
                  )}
                </div>
                {c.acreedor && (
                  <p className="text-sm font-medium">{c.acreedor}</p>
                )}
                {c.descripcion && (
                  <p className="text-sm mt-0.5 opacity-90">{c.descripcion}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {cargas.length === 0 && (refs_catastrales.length > 0 || titulares.length > 0) && (
        <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-lg px-4 py-3">
          <CheckCircle size={16} className="text-green-600" />
          <p className="text-sm text-green-800">Sin cargas registradas en el documento</p>
        </div>
      )}

      {/* Titulares */}
      {titulares.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b flex items-center gap-2">
            <User size={16} className="text-gray-500" />
            <span className="text-sm font-medium text-gray-700">
              Titulares ({titulares.length})
            </span>
          </div>
          <div className="divide-y">
            {titulares.map((t, i) => (
              <div key={i} className="px-4 py-3 flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-900">{t.nombre || '—'}</p>
                  {t.nif && <p className="text-xs text-gray-500">{t.nif}</p>}
                </div>
                {t.porcentaje_propiedad && (
                  <span className="text-sm font-semibold text-sky-700">
                    {t.porcentaje_propiedad}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Superficies */}
      {haySuperficies && (
        <div className="grid grid-cols-3 gap-3">
          {superficies.construida_m2 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
              <Home size={20} className="mx-auto mb-2 text-sky-500" />
              <p className="text-lg font-bold text-gray-900">{superficies.construida_m2} m²</p>
              <p className="text-xs text-gray-500">Construida</p>
            </div>
          )}
          {superficies.util_m2 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
              <Home size={20} className="mx-auto mb-2 text-green-500" />
              <p className="text-lg font-bold text-gray-900">{superficies.util_m2} m²</p>
              <p className="text-xs text-gray-500">Util</p>
            </div>
          )}
          {superficies.parcela_m2 && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
              <Home size={20} className="mx-auto mb-2 text-amber-500" />
              <p className="text-lg font-bold text-gray-900">{superficies.parcela_m2} m²</p>
              <p className="text-xs text-gray-500">Parcela</p>
            </div>
          )}
        </div>
      )}

      {/* Datos principales */}
      {hayDatos && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b text-sm font-medium text-gray-700">
            Datos del documento
          </div>
          <table className="w-full text-sm">
            <tbody className="divide-y">
              {Object.entries(datosDict).map(([k, v]) => (
                <tr key={k} className="hover:bg-gray-50">
                  <td className="px-4 py-2.5 text-gray-500 w-2/5">{k}</td>
                  <td className="px-4 py-2.5 text-gray-900 font-medium">{String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Referencias catastrales y registrales */}
      {(refs_catastrales.length > 0 || refs_registrales.length > 0) && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b text-sm font-medium text-gray-700">
            Referencias
          </div>
          <div className="p-4 space-y-3">
            {refs_catastrales.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1.5">Catastrales</p>
                <div className="flex flex-wrap gap-2">
                  {refs_catastrales.map((rc, i) => (
                    <span key={i} className="px-3 py-1 rounded-full bg-sky-50 border border-sky-200 text-sky-800 text-xs font-mono">
                      {rc}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {refs_registrales.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1.5">Registrales</p>
                <div className="space-y-1">
                  {refs_registrales.map((r, i) => (
                    <p key={i} className="text-xs text-gray-700 font-mono bg-gray-50 px-3 py-1.5 rounded">
                      {[r.tomo && `T.${r.tomo}`, r.libro && `L.${r.libro}`, r.folio && `F.${r.folio}`, r.finca && `Finca ${r.finca}`]
                        .filter(Boolean).join(' · ')}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Fechas relevantes */}
      {hayFechas && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b flex items-center gap-2">
            <Calendar size={16} className="text-gray-500" />
            <span className="text-sm font-medium text-gray-700">Fechas relevantes</span>
          </div>
          <div className="grid grid-cols-3 divide-x">
            {fechas.otorgamiento && (
              <div className="px-4 py-3">
                <p className="text-xs text-gray-500 mb-1">Otorgamiento</p>
                <p className="text-sm font-medium text-gray-900">{fechas.otorgamiento}</p>
              </div>
            )}
            {fechas.inscripcion && (
              <div className="px-4 py-3">
                <p className="text-xs text-gray-500 mb-1">Inscripcion</p>
                <p className="text-sm font-medium text-gray-900">{fechas.inscripcion}</p>
              </div>
            )}
            {fechas.caducidad && (
              <div className="px-4 py-3">
                <p className="text-xs text-gray-500 mb-1">Caducidad</p>
                <p className={`text-sm font-medium ${fechas.caducidad ? 'text-amber-700' : 'text-gray-900'}`}>
                  {fechas.caducidad}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Condiciones relevantes */}
      {condiciones.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b text-sm font-medium text-gray-700">
            Condiciones y clausulas relevantes
          </div>
          <ul className="divide-y">
            {condiciones.map((c, i) => (
              <li key={i} className="px-4 py-3 text-sm text-gray-700 flex items-start gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-gray-400 flex-shrink-0 mt-1.5" />
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
