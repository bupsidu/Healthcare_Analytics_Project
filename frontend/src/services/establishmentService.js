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
   /**
   * Resuelve dinámicamente el establecimiento del usuario autenticado.
   */
  async resolverEstablecimiento(usuario) {
    // 1. Si el usuario ya trae su hospital en memoria
    if (usuario?.establecimiento) {
      return usuario.establecimiento
    }

    // 2. Si no lo tiene en memoria, consultarlo directamente al endpoint /api/auth/me
    try {
      const token = authClient.getToken()
      if (token) {
        const resp = await fetch(`${API_BASE_URL}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (resp.ok) {
          const userData = await resp.json()
          if (userData.establecimiento) {
            // Actualizar la sesión guardada en localStorage
            const sesionLocal = JSON.parse(localStorage.getItem('hospital_user') || '{}')
            sesionLocal.establecimiento = userData.establecimiento
            localStorage.setItem('hospital_user', JSON.stringify(sesionLocal))
            return userData.establecimiento
          }
        }
      }
    } catch (err) {
      console.warn('No fue posible obtener el establecimiento desde el backend:', err)
    }

    return null
  }
}