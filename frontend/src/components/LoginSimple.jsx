import React, { useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export function LoginSimple({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mensaje, setMensaje] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (event) => {
    event.preventDefault()
    setMensaje('Validando credenciales...')
    setIsSubmitting(true)

    try {
      const response = await fetch(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username: email, password }),
      })
      const data = await response.json()

      if (!response.ok) {
        setMensaje(`Error de login: ${data.detail || 'Credenciales inválidas'}`)
        return
      }

      localStorage.setItem('token', data.access_token)
      onLogin()
    } catch {
      setMensaje('Error de conexión: no se pudo conectar con la API en http://localhost:8000.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="login-panel">
      <h2>Acceso personal médico</h2>
      <p className="login-help">Ingresa un usuario registrado en PostgreSQL.</p>

      <form className="login-form" onSubmit={handleSubmit}>
        <label htmlFor="email">Correo electrónico</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="medico@hospital.cl"
          autoComplete="email"
          required
        />

        <label htmlFor="password">Contraseña</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
        />

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Validando...' : 'Iniciar sesión'}
        </button>
      </form>

      {mensaje && <p className="login-message" role="status">{mensaje}</p>}
    </div>
  )
}
