import { useState } from 'react'
import { Search } from 'lucide-react'
import { catastroApi } from '../../api/client'
import { useAppStore } from '../../stores/appStore'

const PROVINCIAS = [
  { value: 'CANTABRIA', label: 'Cantabria' },
  { value: 'ASTURIAS', label: 'Asturias' },
]

export function CatastroPanel() {
  const { setLoading, setCurrentResult } = useAppStore()
  const [rc, setRc] = useState('')
  const [provincia, setProvincia] = useState('CANTABRIA')
  const [municipio, setMunicipio] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<any>(null)

  const handleConsulta = async () => {
    if (!rc || !municipio) {
      setError('RC y municipio son obligatorios')
      return
    }
    setError(null)
    setLoading(true, 'Consultando Catastro OVC...')
    try {
      const data = await catastroApi.dnprc({ provincia, municipio: municipio.toUpperCase(), rc })
      setResultado(data)
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
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="font-medium text-gray-900 mb-3">Resultado</h3>
          <pre className="text-xs bg-gray-50 rounded-lg p-4 overflow-auto max-h-96">
            {JSON.stringify(resultado, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}
