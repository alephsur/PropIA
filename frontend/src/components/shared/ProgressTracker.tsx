import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { tareasApi } from '../../api/client'

interface ProgressTrackerProps {
  tareaId: string
  total: number
  onDone: () => void
}

export function ProgressTracker({ tareaId, total, onDone }: ProgressTrackerProps) {
  const { data } = useQuery({
    queryKey: ['tarea', tareaId],
    queryFn: () => tareasApi.get(tareaId),
    refetchInterval: (query) => query.state.data?.status === 'done' ? false : 2000,
  })

  useEffect(() => {
    if (data?.status === 'done') onDone()
  }, [data?.status])

  const procesados = data?.detalle?.procesados ?? 0
  const pct = total > 0 ? Math.round((procesados / total) * 100) : 0

  return (
    <div className="space-y-3 p-4 border rounded-xl bg-green-50 border-green-200">
      <p className="text-sm font-medium text-green-800">
        {data?.mensaje ?? 'Iniciando...'}
      </p>
      <div className="w-full bg-green-200 rounded-full h-2">
        <div
          className="bg-green-600 h-2 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-green-700">{pct}% completado</p>
    </div>
  )
}
