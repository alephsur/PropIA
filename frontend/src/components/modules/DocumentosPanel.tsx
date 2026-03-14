import { useState, useRef } from 'react'
import { Upload, FileSearch } from 'lucide-react'
import { documentosApi } from '../../api/client'

export function DocumentosPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [consulta, setConsulta] = useState('')
  const [resultado, setResultado] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleAnalizar = async () => {
    if (!file) { setError('Selecciona un documento'); return }
    const fd = new FormData()
    fd.append('documento', file)
    if (consulta) fd.append('consulta', consulta)
    setLoading(true); setError(null)
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
        <h2 className="text-xl font-semibold text-gray-900">Análisis de Documentos</h2>
        <p className="text-sm text-gray-500 mt-1">Extrae información de escrituras, notas simples y más</p>
      </div>
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-sky-400 transition-colors">
          <Upload className="mx-auto mb-2 text-gray-400" size={32} />
          <p className="text-sm text-gray-600">
            {file ? file.name : 'Arrastra un PDF o imagen, o haz clic para seleccionar'}
          </p>
          <p className="text-xs text-gray-400 mt-1">PDF, JPG, PNG, WEBP</p>
          <input ref={inputRef} type="file" accept=".pdf,image/*"
            className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </div>
        <textarea value={consulta} onChange={(e) => setConsulta(e.target.value)}
          placeholder="Consulta específica (opcional): ¿Hay hipotecas sobre la finca?"
          rows={2} className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" />
        {error && <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>}
        <button onClick={handleAnalizar} disabled={loading}
          className="flex items-center gap-2 bg-sky-600 hover:bg-sky-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
          <FileSearch size={16} />
          {loading ? 'Analizando...' : 'Analizar documento'}
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
