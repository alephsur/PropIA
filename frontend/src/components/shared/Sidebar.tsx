import { Building2, Map, FileText, FileSearch, Library } from 'lucide-react'
import { useAppStore, Module } from '../../stores/appStore'

const MODULES: { id: Module; label: string; icon: React.ElementType; badge?: string }[] = [
  { id: 'catastro', label: 'Catastro', icon: Building2 },
  { id: 'urbanismo', label: 'Planeamiento', icon: Map },
  { id: 'normativa', label: 'Normativa', icon: FileText },
  { id: 'documentos', label: 'Documentos', icon: FileSearch },
  { id: 'biblioteca', label: 'Biblioteca', icon: Library, badge: 'Nuevo' },
]

export function Sidebar() {
  const { activeModule, setActiveModule } = useAppStore()

  return (
    <aside className="w-64 min-h-screen bg-gray-900 text-white flex flex-col">
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-sky-500 rounded-lg flex items-center justify-center">
            <Building2 size={18} />
          </div>
          <div>
            <div className="font-bold text-white">PropIA</div>
            <div className="text-xs text-gray-400">v3.0 · Cantabria & Asturias</div>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-4 space-y-1">
        {MODULES.map(({ id, label, icon: Icon, badge }) => (
          <button
            key={id}
            onClick={() => setActiveModule(id)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left
              ${activeModule === id
                ? 'bg-sky-600 text-white'
                : 'text-gray-400 hover:bg-gray-800 hover:text-white'}`}>
            <Icon size={18} />
            <span className="flex-1">{label}</span>
            {badge && (
              <span className="text-xs bg-sky-500 text-white px-1.5 py-0.5 rounded-full">{badge}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="p-4 border-t border-gray-800">
        <div className="text-xs text-gray-500 text-center">
          🏠 Automatización Inmobiliaria
        </div>
      </div>
    </aside>
  )
}
