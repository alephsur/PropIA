import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { tareasApi } from '../../api/client'
import { AlertTriangle, CheckCircle } from 'lucide-react'

interface ProgressTrackerProps {
  tareaId: string
  total: number
  onDone: () => void
}

const DONE_STATUSES = ['done', 'done_with_errors']

export function ProgressTracker({ tareaId, total, onDone }: ProgressTrackerProps) {
  const { data } = useQuery({
    queryKey: ['tarea', tareaId],
    queryFn: () => tareasApi.get(tareaId),
    refetchInterval: (query) =>
      DONE_STATUSES.includes(query.state.data?.status) ? false : 2000,
  })

  const isDone = DONE_STATUSES.includes(data?.status)
  const hasErrors = data?.status === 'done_with_errors'
  const errores: { nombre: string; fase: string; error: string }[] = data?.detalle?.errores ?? []
  const procesados = data?.detalle?.procesados ?? 0
  const pct = total > 0 ? Math.round((procesados / total) * 100) : 0

  useEffect(() => {
    if (isDone) onDone()
  }, [isDone])

  return (
    <div className={`space-y-3 p-4 border rounded-xl ${
      hasErrors
        ? 'bg-amber-50 border-amber-200'
        : isDone
        ? 'bg-green-50 border-green-200'
        : 'bg-blue-50 border-blue-200'
    }`}>
      <div className="flex items-center gap-2">
        {hasErrors
          ? <AlertTriangle size={16} className="text-amber-600 flex-shrink-0" />
          : isDone
          ? <CheckCircle size={16} className="text-green-600 flex-shrink-0" />
          : null}
        <p className={`text-sm font-medium ${
          hasErrors ? 'text-amber-800' : isDone ? 'text-green-800' : 'text-blue-800'
        }`}>
          {data?.mensaje ?? 'Iniciando...'}
        </p>
      </div>

      {!isDone && (
        <>
          <div className="w-full bg-blue-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-xs text-blue-700">{pct}% completado</p>
        </>
      )}

      {errores.length > 0 && (
        <div className="mt-2 space-y-1">
          <p className="text-xs font-medium text-amber-700">Errores encontrados:</p>
          <ul className="space-y-1 max-h-40 overflow-y-auto">
            {errores.map((e, idx) => (
              <li key={idx} className="text-xs bg-white border border-amber-200 rounded px-3 py-2">
                <span className="font-medium text-gray-800">{e.nombre}</span>
                <span className="text-amber-600 ml-2">({e.fase})</span>
                <p className="text-gray-500 mt-0.5 break-all">{e.error}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
