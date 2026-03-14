interface Documento {
  nombre: string
  seccion: string
  url_origen: string
  tamanio_kb?: number
}

interface ConfirmDialogProps {
  documentos: Documento[]
  onConfirm: (docs: Documento[]) => void
  onCancel: () => void
}

const SECCIONES_NO_INDEXAR = ['Planos', 'Boletín']

export function ConfirmDialog({ documentos, onConfirm, onCancel }: ConfirmDialogProps) {
  const indexables = documentos.filter((d) => !SECCIONES_NO_INDEXAR.includes(d.seccion))
  const noIndexables = documentos.length - indexables.length
  const totalKb = documentos.reduce((s, d) => s + (d.tamanio_kb || 0), 0)
  const totalMb = (totalKb / 1024).toFixed(1)

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-lg w-full">
        <div className="p-6 border-b">
          <h3 className="font-semibold text-gray-900">Confirmar descarga de documentos</h3>
        </div>
        <div className="p-6 space-y-4">
          <div className="max-h-64 overflow-y-auto space-y-2">
            {documentos.map((d) => (
              <div key={d.url_origen} className="flex items-center justify-between py-1 text-sm">
                <span className="text-gray-800 truncate mr-3">{d.nombre}</span>
                <span className={`flex-shrink-0 px-2 py-0.5 rounded-full text-xs font-medium
                  ${d.seccion === 'Normativa' ? 'bg-green-100 text-green-700' :
                    d.seccion === 'Memoria' ? 'bg-blue-100 text-blue-700' :
                    d.seccion === 'Planos' ? 'bg-gray-100 text-gray-600' :
                    d.seccion === 'PEPRI' ? 'bg-purple-100 text-purple-700' :
                    'bg-orange-100 text-orange-700'}`}>
                  {d.seccion}
                </span>
              </div>
            ))}
          </div>
          <div className="bg-sky-50 border border-sky-200 rounded-lg p-3 text-sm text-sky-800">
            Se descargarán <strong>{documentos.length}</strong> documentos ({totalMb} MB).{' '}
            <strong>{indexables.length}</strong> se indexarán para búsqueda IA.
            {noIndexables > 0 && <> <strong>{noIndexables}</strong> (planos/boletines) se descargarán solo para consulta visual.</>}
          </div>
          <div className="bg-gray-50 border rounded-lg p-3 text-xs text-gray-600">
            ℹ Los documentos ya descargados previamente para este municipio se omitirán automáticamente.
          </div>
        </div>
        <div className="p-4 border-t flex justify-end gap-3">
          <button onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-700 border rounded-lg hover:bg-gray-50">
            Cancelar
          </button>
          <button onClick={() => onConfirm(documentos)}
            className="px-4 py-2 text-sm bg-sky-600 text-white rounded-lg hover:bg-sky-700">
            Confirmar descarga
          </button>
        </div>
      </div>
    </div>
  )
}
