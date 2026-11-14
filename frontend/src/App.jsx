// frontend/src/App.jsx
import React, { useState, useEffect } from 'react'
import LoginView from './components/auth/LoginView'
import MainLayout from './components/layout/MainLayout'
import { authClient } from './services/authClient'

export default function App() {
  const [usuario, setUsuario] = useState(null)
  const [comprobandoSesion, setComprobandoSesion] = useState(true)

  useEffect(() => {
    const sesionGuardada = authClient.getSesionActual()
    if (sesionGuardada) {
      setUsuario(sesionGuardada.user)
    }
    setComprobandoSesion(false)
  }, [])

  const handleCerrarSesion = () => {
    authClient.logout()
    setUsuario(null)
  }

  if (comprobandoSesion) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-clinical-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  // 1. Si no hay sesión -> Muestra Login
  if (!usuario) {
    return <LoginView onLoginSuccess={(user) => setUsuario(user)} />
  }

  // 2. Si hay sesión -> Muestra el Cascarón Maestro con Dashboard arriba y Triage abajo
  return (
    <MainLayout usuario={usuario} onLogout={handleCerrarSesion} />
  )
}