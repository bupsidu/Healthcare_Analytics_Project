// frontend/src/services/authClient.js

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const authClient = {
  /**
   * Inicia sesión contra el backend de FastAPI y PostgreSQL.
   * @param {string} email - Correo del funcionario de salud
   * @param {string} password - Contraseña en texto plano
   * @returns {Promise<Object>} Datos del usuario autenticado y su token
   */
  async login(email, password) {
    if (!email || !password) {
      throw new Error('Por favor ingrese su correo y contraseña.')
    }

    let tokenData
    
    // 1. Enviar credenciales a POST /api/auth/login
    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({
          username: email.trim().toLowerCase(),
          password: password,
        }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Credenciales incorrectas. Verifique correo y contraseña.')
      }

      tokenData = data
    } catch (error) {
      // Si el backend no responde o está apagado
      if (error.name === 'TypeError' && error.message.includes('fetch')) {
        throw new Error('No se pudo conectar con el servidor backend en http://localhost:8000. Asegúrese de que FastAPI esté encendido.')
      }
      throw error
    }

    // 2. Con el Token recibido, consultar los datos del usuario en GET /api/auth/me
    try {
      const meResponse = await fetch(`${API_BASE_URL}/auth/me`, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${tokenData.access_token}`,
        },
      })

      if (!meResponse.ok) {
        throw new Error('No se pudo obtener el perfil del usuario desde la base de datos.')
      }

      const userData = await meResponse.json()

      const session = {
        token: tokenData.access_token,
        tokenType: tokenData.token_type,
        user: {
          id: userData.id,
          email: userData.email,
          nombre: userData.full_name || 'Personal Médico',
          rol: userData.role || 'medico',
        },
      }

      // 3. Guardar en almacenamiento local
      localStorage.setItem('hospital_token', session.token)
      localStorage.setItem('hospital_user', JSON.stringify(session.user))

      return session
    } catch (error) {
      throw error
    }
  },

  /**
   * Recupera la sesión guardada en el navegador si existe.
   */
  getSesionActual() {
    try {
      const token = localStorage.getItem('hospital_token')
      const userStr = localStorage.getItem('hospital_user')
      if (token && userStr) {
        return {
          token,
          user: JSON.parse(userStr),
        }
      }
      return null
    } catch {
      return null
    }
  },

  /**
   * Obtiene el token de autenticación para futuras peticiones.
   */
  getToken() {
    return localStorage.getItem('hospital_token')
  },

  /**
   * Cierra la sesión activa en el navegador.
   */
  logout() {
    localStorage.removeItem('hospital_token')
    localStorage.removeItem('hospital_user')
  },
}