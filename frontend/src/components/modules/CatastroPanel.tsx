import { useState } from 'react'
import { Search, Copy, Check, Map } from 'lucide-react'
import { catastroApi } from '../../api/client'
import { useAppStore } from '../../stores/appStore'

const PROVINCIAS = [
  { value: 'CANTABRIA', label: 'Cantabria' },
  { value: 'ASTURIAS', label: 'Asturias' },
]

interface DatosCatastro {
  referencia_catastral: string | null
  clase: string | null
  direccion: string | null
  municipio: string | null
  provincia: string | null
  codigo_postal: string | null
  uso: string | null
  superficie_construida_m2: number | null
  superficie_parcela_m2: number | null
  ano_construccion: number | null
  valor_catastral: number | null
  coeficiente_participacion: string | null
}

function Campo({ label, value }: { label: string; value: React.ReactNode }) {
  if (!value) return null
  return (
    <div className="grid grid-cols-[180px_1fr] gap-4 py-3 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-500 text-right self-start pt-0.5">{label}</span>
      <span className="text-sm font-medium text-gray-900">{value}</span>
    </div>
  )
}

function RCCopyable({ rc }: { rc: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(rc)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <span className="inline-flex items-center gap-2 font-mono">
      {rc}
      <button
        onClick={handleCopy}
        className="text-gray-400 hover:text-gray-700 transition-colors"
        title="Copiar RC"
      >
        {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
      </button>
    </span>
  )
}

function SeccionCatastro({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl overflow-hidden border border-gray-200">
      <div className="bg-amber-500 px-5 py-2.5">
        <h3 className="text-sm font-bold text-white tracking-wide uppercase">{titulo}</h3>
      </div>
      <div className="bg-white px-5 py-1">{children}</div>
    </div>
  )
}

export function CatastroPanel() {
  const { setLoading, setCurrentResult, navegarAUrbanismo } = useAppStore()
  const [rc, setRc] = useState('')
  const [provincia, setProvincia] = useState('CANTABRIA')
  const [municipio, setMunicipio] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<DatosCatastro | null>(null)

  const handleConsulta = async () => {
    if (!rc || !municipio) {
      setError('RC y municipio son obligatorios')
      return
    }
    setError(null)
    setLoading(true, 'Consultando Catastro OVC...')
    try {
      const data = await catastroApi.dnprc({ provincia, municipio: municipio.toUpperCase(), rc })
      setResultado(data as DatosCatastro)
      setCurrentResult(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Catastro</h2>
        <p className="text-sm text-gray-500 mt-1">Consulta datos catastrales por referencia o dirección</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Provincia</label>
            <select
              value={provincia}
              onChange={(e) => setProvincia(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              {PROVINCIAS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Municipio</label>
            <input
              type="text"
              value={municipio}
              onChange={(e) => setMunicipio(e.target.value)}
              placeholder="Ej: SAN VICENTE DE LA BARQUERA"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Referencia Catastral
          </label>
          <input
            type="text"
            value={rc}
            onChange={(e) => setRc(e.target.value.toUpperCase())}
            placeholder="Ej: 6646704UP8064N0001ST"
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-500"
          />
          <p className="text-xs text-gray-400 mt-1">14, 18 o 20 caracteres</p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}

        <button
          onClick={handleConsulta}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Search size={16} />
          Consultar Catastro
        </button>
      </div>

      {resultado && (
        <div className="space-y-4">
          {/* Acceso rápido a Planeamiento con esta RC */}
          {resultado.referencia_catastral && resultado.municipio && (
            <button
              onClick={() =>
                navegarAUrbanismo(
                  resultado.municipio!.toUpperCase(),
                  (resultado.provincia ?? provincia).toLowerCase(),
                  resultado.referencia_catastral!
                )
              }
              className="w-full flex items-center justify-center gap-2 border-2 border-sky-500 text-sky-600 hover:bg-sky-50 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors"
            >
              <Map size={16} />
              Consultar PGOU con esta RC
            </button>
          )}

          <SeccionCatastro titulo="Datos descriptivos del inmueble">
            {resultado.referencia_catastral && (
              <Campo label="Referencia catastral" value={<RCCopyable rc={resultado.referencia_catastral} />} />
            )}
            <Campo label="Localización" value={resultado.direccion} />
            <Campo label="Clase" value={resultado.clase} />
            <Campo label="Uso principal" value={resultado.uso} />
            {resultado.ano_construccion && (
              <Campo label="Año de construcción" value={resultado.ano_construccion} />
            )}
            {resultado.coeficiente_participacion && (
              <Campo label="Coef. participación" value={`${resultado.coeficiente_participacion} %`} />
            )}
          </SeccionCatastro>

          {(resultado.superficie_parcela_m2 || resultado.superficie_construida_m2) && (
            <SeccionCatastro titulo="Parcela catastral">
              <Campo label="Localización" value={
                resultado.municipio
                  ? `${resultado.municipio}${resultado.provincia ? ` (${resultado.provincia})` : ''}`
                  : null
              } />
              {resultado.superficie_parcela_m2 && (
                <Campo label="Superficie gráfica" value={`${resultado.superficie_parcela_m2} m²`} />
              )}
              {resultado.superficie_construida_m2 && (
                <Campo label="Superficie construida" value={`${resultado.superficie_construida_m2} m²`} />
              )}
            </SeccionCatastro>
          )}
        </div>
      )}
    </div>
  )
}
