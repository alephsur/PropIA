import { X, ExternalLink } from 'lucide-react'

interface PdfViewerProps {
  documentoId: string
  nombre: string
  onClose: () => void
}

export function PdfViewer({ documentoId, nombre, onClose }: PdfViewerProps) {
  const url = `/api/biblioteca/documento/${documentoId}`

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex flex-col">
      <div className="bg-white border-b px-4 py-2 flex items-center justify-between">
        <span className="font-medium text-sm truncate max-w-lg">{nombre}</span>
        <div className="flex gap-2 flex-shrink-0">
          <button
            onClick={() => window.open(url, '_blank')}
            className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900 px-3 py-1 rounded-lg border hover:bg-gray-50">
            <ExternalLink size={14} />
            Nueva pestaña
          </button>
          <button onClick={onClose}
            className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900 px-3 py-1 rounded-lg hover:bg-gray-100">
            <X size={14} />
            Cerrar
          </button>
        </div>
      </div>
      <iframe src={url} className="flex-1 w-full" title={nombre} />
    </div>
  )
}
