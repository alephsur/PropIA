import { useState } from 'react'
import { FileText } from 'lucide-react'
import { normativaApi } from '../../api/client'

export function NormativaPanel() {
  const [ccaa, setCcaa] = useState<'cantabria' | 'asturias'>('cantabria')
  const [q, setQ] = useState('')
  const [resultados, setResultados] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleBuscar = async () => {
    if (!q) return
    setLoading(true); setError(null)
    try {
      const fn = ccaa === 'cantabria' ? normativaApi.boc : normativaApi.bopa
      const data = await fn(q)
      setResultados(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Normativa</h2>
        <p className="text-sm text-gray-500 mt-1">Búsqueda en BOC (Cantabria) y BOPA (Asturias)</p>
      </div>
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div className="flex gap-2">
          {(['cantabria', 'asturias'] as const).map((c) => (
            <button key={c} onClick={() => setCcaa(c)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                ccaa === c ? 'bg-sky-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}>
              {c === 'cantabria' ? 'BOC Cantabria' : 'BOPA Asturias'}
            </button>
          ))}
        </div>
        <input type="text" value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleBuscar()}
          placeholder="Ej: vivienda turística, licencia obras..."
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}
        <button onClick={handleBuscar} disabled={loading}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
          <FileText size={16} />
          {loading ? 'Buscando...' : 'Buscar normativa'}
        </button>
      </div>
      {resultados.length > 0 && (
        <div className="space-y-2">
          {resultados.map((r, i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 p-4">
              <p className="text-sm font-medium text-gray-900">{r.titulo}</p>
              {r.fecha && <p className="text-xs text-gray-500 mt-1">{r.fecha}</p>}
              {r.url && <a href={r.url} target="_blank" rel="noopener noreferrer"
                className="text-xs text-sky-600 hover:underline mt-1 block">Ver documento →</a>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
