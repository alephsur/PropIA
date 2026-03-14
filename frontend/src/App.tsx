import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from './components/shared/Sidebar'
import { CatastroPanel } from './components/modules/CatastroPanel'
import { UrbanismoPanel } from './components/modules/UrbanismoPanel'
import { NormativaPanel } from './components/modules/NormativaPanel'
import { DocumentosPanel } from './components/modules/DocumentosPanel'
import { BibliotecaPanel } from './components/modules/BibliotecaPanel'
import { useAppStore } from './stores/appStore'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

function AppContent() {
  const { activeModule, isLoading, loadingStep } = useAppStore()

  const Panel = {
    catastro: CatastroPanel,
    urbanismo: UrbanismoPanel,
    normativa: NormativaPanel,
    documentos: DocumentosPanel,
    biblioteca: BibliotecaPanel,
  }[activeModule]

  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        {isLoading && (
          <div className="fixed top-4 right-4 z-40 bg-sky-600 text-white px-4 py-2 rounded-lg shadow-lg text-sm flex items-center gap-2">
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            {loadingStep || 'Cargando...'}
          </div>
        )}
        <div className="max-w-4xl mx-auto">
          <Panel />
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppContent />
    </QueryClientProvider>
  )
}
