import { create } from 'zustand'

export type Module = 'catastro' | 'urbanismo' | 'normativa' | 'documentos' | 'biblioteca'

interface DocumentoExplorado {
  nombre: string
  url_origen: string
  seccion: string
  extension: string
  tamanio_kb?: number
}

interface AppStore {
  activeModule: Module
  setActiveModule: (m: Module) => void

  currentResult: any | null
  setCurrentResult: (r: any) => void

  isLoading: boolean
  loadingStep: string
  setLoading: (v: boolean, step?: string) => void

  sessionHistory: any[]
  addToHistory: (item: any) => void

  municipiosIndexados: any[]
  setMunicipiosIndexados: (m: any[]) => void

  // Biblioteca
  documentosExplorados: DocumentoExplorado[]
  setDocumentosExplorados: (d: DocumentoExplorado[]) => void

  municipioBiblioteca: string | null
  setMunicipioBiblioteca: (m: string | null) => void

  provinciaBiblioteca: string | null
  setProvinciaBiblioteca: (p: string | null) => void

  ccaaActiva: string
  setCcaaActiva: (ccaa: string) => void

  // Urbanismo — pre-rellenado al navegar desde Catastro o Biblioteca
  municipioUrbanismo: string
  provinciaUrbanismo: string
  rcUrbanismo: string
  setUrbanismoTarget: (municipio: string, provincia: string) => void
  navegarAUrbanismo: (municipio: string, provincia: string, rc?: string) => void
}

export const useAppStore = create<AppStore>((set) => ({
  activeModule: 'catastro',
  setActiveModule: (m) => set({ activeModule: m }),

  currentResult: null,
  setCurrentResult: (r) => set({ currentResult: r }),

  isLoading: false,
  loadingStep: '',
  setLoading: (v, step = '') => set({ isLoading: v, loadingStep: step }),

  sessionHistory: [],
  addToHistory: (item) =>
    set((s) => ({
      sessionHistory: [item, ...s.sessionHistory].slice(0, 20),
    })),

  municipiosIndexados: [],
  setMunicipiosIndexados: (m) => set({ municipiosIndexados: m }),

  documentosExplorados: [],
  setDocumentosExplorados: (d) => set({ documentosExplorados: d }),

  municipioBiblioteca: null,
  setMunicipioBiblioteca: (m) => set({ municipioBiblioteca: m }),

  provinciaBiblioteca: null,
  setProvinciaBiblioteca: (p) => set({ provinciaBiblioteca: p }),

  ccaaActiva: 'cantabria',
  setCcaaActiva: (ccaa) => set({ ccaaActiva: ccaa }),

  municipioUrbanismo: '',
  provinciaUrbanismo: 'cantabria',
  rcUrbanismo: '',
  setUrbanismoTarget: (municipio, provincia) =>
    set({ municipioUrbanismo: municipio, provinciaUrbanismo: provincia }),
  navegarAUrbanismo: (municipio, provincia, rc = '') =>
    set({ activeModule: 'urbanismo', municipioUrbanismo: municipio, provinciaUrbanismo: provincia, rcUrbanismo: rc }),
}))
