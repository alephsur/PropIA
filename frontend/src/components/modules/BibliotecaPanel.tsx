import { useState } from 'react'
import { Library, Search, Download, Eye, Trash2, CheckSquare, Square } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { bibliotecaApi } from '../../api/client'
import { PdfViewer } from '../shared/PdfViewer'
import { ConfirmDialog } from '../shared/ConfirmDialog'
import { ProgressTracker } from '../shared/ProgressTracker'

const SECCIONES_NO_INDEXAR = ['Planos', 'Boletín']
const SECCION_COLORS: Record<string, string> = {
  Normativa: 'bg-green-100 text-green-700',
  Memoria: 'bg-blue-100 text-blue-700',
  Fichas: 'bg-orange-100 text-orange-700',
  Planos: 'bg-gray-100 text-gray-500',
  PEPRI: 'bg-purple-100 text-purple-700',
  Criterios: 'bg-red-100 text-red-700',
  Catálogo: 'bg-indigo-100 text-indigo-700',
  Boletín: 'bg-yellow-100 text-yellow-700',
  Otros: 'bg-gray-100 text-gray-600',
}

type Tab = 'explorador' | 'biblioteca'

export function BibliotecaPanel() {
  const [tab, setTab] = useState<Tab>('explorador')

  // Explorador state
  const [url, setUrl] = useState('')
  const [provincia, setProvincia] = useState('cantabria')
  const [municipio, setMunicipio] = useState('')
  const [docsEncontrados, setDocsEncontrados] = useState<any[]>([])
  const [seleccionados, setSeleccionados] = useState<Set<string>>(new Set())
  const [explorando, setExplorando] = useState(false)
  const [errorExplorar, setErrorExplorar] = useState<string | null>(null)
  const [showConfirm, setShowConfirm] = useState(false)
  const [tareaId, setTareaId] = useState<string | null>(null)
  const [totalDescarga, setTotalDescarga] = useState(0)

  // Biblioteca state
  const [viewerDoc, setViewerDoc] = useState<{ id: string; nombre: string } | null>(null)
  const [municipioBiblio, setMunicipioBiblio] = useState('')
  const [provinciaBiblio, setProvinciaBiblio] = useState('cantabria')

  const { data: docsBiblioteca, refetch: refetchBiblio } = useQuery({
    queryKey: ['biblioteca', municipioBiblio, provinciaBiblio],
    queryFn: () => bibliotecaApi.listarMunicipio(municipioBiblio, provinciaBiblio),
    enabled: !!municipioBiblio,
  })

  const handleExplorar = async () => {
    if (!url || !municipio) { setErrorExplorar('URL y municipio son obligatorios'); return }
    setExplorando(true); setErrorExplorar(null); setDocsEncontrados([])
    try {
      const docs = await bibliotecaApi.explorar({ url, municipio, provincia })
      setDocsEncontrados(docs)
      // Pre-seleccionar todo excepto planos
      const sel = new Set<string>(
        docs.filter((d: any) => !SECCIONES_NO_INDEXAR.includes(d.seccion))
          .map((d: any) => d.url_origen)
      )
      setSeleccionados(sel)
    } catch (e: any) {
      setErrorExplorar(e.message)
    } finally {
      setExplorando(false)
    }
  }

  const toggleSeleccion = (url: string, seccion: string) => {
    if (SECCIONES_NO_INDEXAR.includes(seccion)) return // planos siempre deshabilitados
    setSeleccionados((prev) => {
      const next = new Set(prev)
      next.has(url) ? next.delete(url) : next.add(url)
      return next
    })
  }

  const handleDescargar = async (docs: any[]) => {
    setShowConfirm(false)
    try {
      const { tarea_id } = await bibliotecaApi.descargar({ municipio, provincia, documentos: docs })
      setTareaId(tarea_id)
      setTotalDescarga(docs.length)
    } catch (e: any) {
      setErrorExplorar(e.message)
    }
  }

  const docsSeleccionados = docsEncontrados.filter((d) => seleccionados.has(d.url_origen))

  const handleEliminar = async (id: string) => {
    if (!confirm('¿Eliminar este documento?')) return
    await bibliotecaApi.eliminarDocumento(id)
    refetchBiblio()
  }

  // Group by section
  const docsPorSeccion = docsEncontrados.reduce((acc: Record<string, any[]>, doc) => {
    const s = doc.seccion || 'Otros'
    if (!acc[s]) acc[s] = []
    acc[s].push(doc)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Library className="text-sky-600" size={24} />
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Biblioteca de Documentos</h2>
          <p className="text-sm text-gray-500">Explora, descarga y consulta documentos de planeamiento</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        {(['explorador', 'biblioteca'] as Tab[]).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors capitalize
              ${tab === t ? 'bg-white shadow-sm text-gray-900' : 'text-gray-600 hover:text-gray-900'}`}>
            {t === 'explorador' ? '🔍 Explorador' : '📚 Biblioteca'}
          </button>
        ))}
      </div>

      {/* EXPLORADOR */}
      {tab === 'explorador' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Provincia</label>
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
              <label className="block text-sm font-medium text-gray-700 mb-1">URL página de urbanismo</label>
              <input type="url" value={url} onChange={(e) => setUrl(e.target.value)}
                placeholder="https://aytosanvicentedelabarquera.es/urbanismo/"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono" />
            </div>
            {errorExplorar && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                {errorExplorar}
              </div>
            )}
            <button onClick={handleExplorar} disabled={explorando}
              className="flex items-center gap-2 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium">
              <Search size={16} />
              {explorando ? 'Explorando...' : 'Explorar documentos'}
            </button>
          </div>

          {/* Tarea en progreso */}
          {tareaId && !tareaId.includes('done') && (
            <ProgressTracker
              tareaId={tareaId}
              total={totalDescarga}
              onDone={() => { setTareaId(null); setTab('biblioteca') }}
            />
          )}

          {/* Resultados del scraping */}
          {docsEncontrados.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="p-4 border-b bg-gray-50 flex items-center justify-between">
                <p className="text-sm text-gray-700">
                  Se han encontrado <strong>{docsEncontrados.length}</strong> documentos.
                  Los planos cartográficos no se indexarán.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setSeleccionados(new Set(
                      docsEncontrados.filter((d) => !SECCIONES_NO_INDEXAR.includes(d.seccion))
                        .map((d) => d.url_origen)
                    ))}
                    className="text-xs px-3 py-1 rounded-lg border hover:bg-gray-100">
                    Marcar todos
                  </button>
                  <button
                    onClick={() => setSeleccionados(new Set())}
                    className="text-xs px-3 py-1 rounded-lg border hover:bg-gray-100">
                    Desmarcar todos
                  </button>
                  <button
                    onClick={() => setShowConfirm(true)}
                    disabled={seleccionados.size === 0}
                    className="flex items-center gap-1 text-xs px-3 py-1 rounded-lg bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-50">
                    <Download size={12} />
                    Descargar seleccionados ({seleccionados.size})
                  </button>
                </div>
              </div>

              <div className="divide-y">
                {Object.entries(docsPorSeccion).map(([seccion, docs]) => (
                  <div key={seccion}>
                    <div className="px-4 py-2 bg-gray-50 border-b">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${SECCION_COLORS[seccion] || SECCION_COLORS.Otros}`}>
                        {seccion}
                      </span>
                    </div>
                    {docs.map((doc) => {
                      const disabled = SECCIONES_NO_INDEXAR.includes(doc.seccion)
                      const checked = seleccionados.has(doc.url_origen)
                      return (
                        <div key={doc.url_origen}
                          onClick={() => toggleSeleccion(doc.url_origen, doc.seccion)}
                          className={`flex items-center gap-3 px-4 py-3 text-sm
                            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-gray-50'}`}>
                          {checked ? <CheckSquare size={16} className="text-sky-600 flex-shrink-0" />
                            : <Square size={16} className="text-gray-400 flex-shrink-0" />}
                          <span className="flex-1 truncate">{doc.nombre}</span>
                          {disabled && (
                            <span className="text-xs text-gray-400 flex-shrink-0">Solo descarga</span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* BIBLIOTECA */}
      {tab === 'biblioteca' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-4 flex gap-4">
            <select value={provinciaBiblio} onChange={(e) => setProvinciaBiblio(e.target.value)}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm">
              <option value="cantabria">Cantabria</option>
              <option value="asturias">Asturias</option>
            </select>
            <input type="text" value={municipioBiblio} onChange={(e) => setMunicipioBiblio(e.target.value)}
              placeholder="Municipio"
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm" />
          </div>

          {docsBiblioteca && docsBiblioteca.length > 0 ? (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-gray-700">Nombre</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-700">Sección</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-700">Indexado</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-700">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {docsBiblioteca.map((doc: any) => (
                    <tr key={doc.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-900 max-w-xs truncate">{doc.nombre}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SECCION_COLORS[doc.seccion] || SECCION_COLORS.Otros}`}>
                          {doc.seccion}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {doc.indexado
                          ? <span className="flex items-center gap-1 text-green-700 text-xs">✓ Indexado</span>
                          : <span className="text-gray-400 text-xs">No indexado</span>}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button onClick={() => setViewerDoc({ id: doc.id, nombre: doc.nombre })}
                            className="p-1 text-gray-500 hover:text-sky-600 rounded">
                            <Eye size={16} />
                          </button>
                          <button onClick={() => handleEliminar(doc.id)}
                            className="p-1 text-gray-500 hover:text-red-600 rounded">
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : municipioBiblio ? (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
              <Library size={40} className="mx-auto mb-3 opacity-40" />
              <p className="text-sm">No hay documentos descargados para {municipioBiblio}</p>
              <button onClick={() => setTab('explorador')}
                className="mt-3 text-sm text-sky-600 hover:underline">
                Ir al Explorador para añadir documentos
              </button>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
              <p className="text-sm">Introduce un municipio para ver sus documentos</p>
            </div>
          )}
        </div>
      )}

      {/* Modales */}
      {showConfirm && (
        <ConfirmDialog
          documentos={docsSeleccionados}
          onConfirm={handleDescargar}
          onCancel={() => setShowConfirm(false)}
        />
      )}
      {viewerDoc && (
        <PdfViewer
          documentoId={viewerDoc.id}
          nombre={viewerDoc.nombre}
          onClose={() => setViewerDoc(null)}
        />
      )}
    </div>
  )
}
