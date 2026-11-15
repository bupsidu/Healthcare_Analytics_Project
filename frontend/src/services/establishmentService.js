// frontend/src/services/establishmentService.js
import { authClient } from './authClient'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const establishmentService = {
  /**
   * Consulta el catálogo oficial de establecimientos en PostgreSQL vía FastAPI.
   */
  async getEstablecimientos() {
    try {
      const token = authClient.getToken()
      const response = await fetch(`${API_BASE_URL}/establecimientos?activo=true`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) return []
      return await response.json()
    } catch {
      return []
    }
  },

  /**
   * Resuelve dinámicamente el establecimiento según las reglas de negocio:
   * 1. Prioridad 1: Si el usuario ya viene con hospital desde PostgreSQL (lo que hará Matías).
   * 2. Prioridad 2: Cruza el dominio del correo (@...) con los centros de la base de datos.
   * 3. Prioridad 3 (Cuentas de prueba): Toma el primer centro disponible en la base de datos.
   */
  async resolverEstablecimiento(usuario) {
    // 1. Si el backend ya le asignó un hospital en la base de datos
    if (usuario?.establecimiento) {
      return usuario.establecimiento
    }

    // 2. Consultar los establecimientos reales guardados en PostgreSQL
    const lista = await this.getEstablecimientos()

    if (lista.length > 0) {
      const email = usuario?.email?.toLowerCase() || ''
      const dominio = email.split('@')[1] || ''
      // Buscar coincidencia real entre el dominio del correo y el nombre o comuna del centro
      const coincidencia = lista.find((est) => {
        const nombreLimpio = est.nombre.toLowerCase()
        const comunaLimpia = est.comuna.toLowerCase()
        return dominio.includes(nombreLimpio) || dominio.includes(comunaLimpia)
      })
      if (coincidencia) {
        return coincidencia
      }
    }
    // Si el usuario no tiene hospital asignado ni su correo coincide con uno real, devuelve null
    return null
  },
}