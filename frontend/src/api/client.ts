import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg = err.response?.data?.detail || err.message || 'Error desconocido'
    return Promise.reject(new Error(msg))
  }
)

// Typed API calls
export const catastroApi = {
  dnprc: (body: { provincia: string; municipio: string; rc: string }) =>
    api.post('/catastro/dnprc', body),
  cpmrc: (body: { provincia: string; municipio: string; rc: string }) =>
    api.post('/catastro/cpmrc', body),
}

export const bibliotecaApi = {
  explorar: (body: { url: string; municipio: string; provincia: string }) =>
    api.post('/biblioteca/explorar', body),
  descargar: (body: { municipio: string; provincia: string; documentos: any[] }) =>
    api.post('/biblioteca/descargar', body),
  listarMunicipio: (municipio: string, provincia: string) =>
    api.get('/biblioteca/municipio', { params: { municipio, provincia } }),
  eliminarDocumento: (id: string) =>
    api.delete(`/biblioteca/documento/${id}`),
  getDocumentoUrl: (id: string) => `/api/biblioteca/documento/${id}`,
}

export const urbanismoApi = {
  informe: (body: { provincia: string; municipio: string; consulta?: string }) =>
    api.post('/urbanismo/informe', body),
  municipiosIndexados: (ccaa?: string) =>
    api.get('/urbanismo/municipios', { params: { ccaa } }),
  consultasTipo: () =>
    api.get('/urbanismo/consultas-tipo'),
}

export const normativaApi = {
  boc: (q: string, fechaDesde?: string) =>
    api.get('/normativa/boc', { params: { q, fecha_desde: fechaDesde } }),
  bopa: (q: string, fechaDesde?: string) =>
    api.get('/normativa/bopa', { params: { q, fecha_desde: fechaDesde } }),
  boe: (q: string, fechaDesde?: string) =>
    api.get('/normativa/boe', { params: { q, fecha_desde: fechaDesde } }),
}

export const tareasApi = {
  get: (tareaId: string) => api.get(`/tareas/${tareaId}`),
}

export const documentosApi = {
  analizar: (formData: FormData) =>
    api.post('/documentos/analizar', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000, // 5 min — modelos locales (Ollama) pueden tardar con documentos grandes
    }),
}
