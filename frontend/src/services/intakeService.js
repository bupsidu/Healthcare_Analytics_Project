// frontend/src/services/intakeService.js
import { authClient } from './authClient'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const intakeService = {
  /**
   * Registra una nueva atención médica en PostgreSQL vía POST /api/ingresos.
   */
  async registrarIngreso({ establecimientoId, grupoEtario, casos = 1 }) {
    const token = authClient.getToken()
    const hoy = new Date().toISOString().split('T')[0]

    const response = await fetch(`${API_BASE_URL}/ingresos`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        fecha: hoy,
        establecimiento_id: establecimientoId,
        casos_respiratorios: casos,
        grupo_etario: grupoEtario,
      }),
    })

    const data = await response.json()
    if (!response.ok) {
      throw new Error(data.detail || 'No fue posible registrar la atención en el sistema.')
    }
    return data
  },

  /**
   * Obtiene el historial de ingresos del establecimiento vía GET /api/ingresos.
   */
  async getHistorialIngresos(establecimientoId) {
    try {
      const token = authClient.getToken()
      const query = establecimientoId ? `?establecimiento_id=${establecimientoId}&limit=50` : '?limit=50'
      const response = await fetch(`${API_BASE_URL}/ingresos${query}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) return []
      const data = await response.json()
      return data.items || []
    } catch {
      return []
    }
  },
}