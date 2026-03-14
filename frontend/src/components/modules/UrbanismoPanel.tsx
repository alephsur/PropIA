import { useState } from 'react'
import { Map } from 'lucide-react'
import { urbanismoApi } from '../../api/client'

export function UrbanismoPanel() {
  const [provincia, setProvincia] = useState('cantabria')
  const [municipio, setMunicipio] = useState('')
  const [consulta, setConsulta] = useState('')
  const [resultado, setResultado] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleConsulta = async () => {
    if (!municipio) { setError('Municipio obligatorio'); return }
    setError(null); setLoading(true)
    try {
      const data = await urbanismoApi.informe({ provincia, municipio, consulta })
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
        <h2 className="text-xl font-semibold text-gray-900">Planeamiento PGOU</h2>
        <p className="text-sm text-gray-500 mt-1">Consulta el plan urbanístico por municipio</p>
      </div>
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">CCAA</label>
            <select value={provincia} onChange={(e) => setProvincia(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm">
              <option value="cantabria">Cantabria</option>
              <option value="asturias">Asturias</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Municipio</label>
            <input type="text" value={municipio} onChange={(e) => setMunicipio(e.target.value)}
              placeholder="Ej: San Vicente de la Barquera"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Consulta</label>
          <textarea value={consulta} onChange={(e) => setConsulta(e.target.value)}
            placeholder="Ej: ¿Cuál es la edificabilidad máxima en suelo urbano residencial?"
            rows={3} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        </div>
        {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}
        <button onClick={handleConsulta} disabled={loading}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium">
          <Map size={16} />
          {loading ? 'Consultando...' : 'Consultar PGOU'}
        </button>
      </div>
      {resultado && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <pre className="text-xs bg-gray-50 rounded-lg p-4 overflow-auto max-h-96">
            {JSON.stringify(resultado, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
