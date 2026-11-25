// frontend/src/components/layout/MainLayout.jsx
import React, { useState, useEffect } from 'react'
import Navbar from './Navbar'
import LiveStatusBar from './LiveStatusBar'
import Footer from './Footer'
import TriageSection from '../triage/TriageSection'
import DashboardSection from '../dashboard/DashboardSection'
import ReportsSection from '../reports/ReportsSection'
import { establishmentService } from '../../services/establishmentService'

export default function MainLayout({ usuario, onLogout, children }) {
  const [establecimiento, setEstablecimiento] = useState(null)
  const [cargandoCentro, setCargandoCentro] = useState(true)
  const [fechaActual, setFechaActual] = useState(new Date())
  const [tabActiva, setTabActiva] = useState('dashboard') // 'dashboard' | 'reportes'

  // Actualización automática del reloj en tiempo real cada 30 segundos
  useEffect(() => {
    const timer = setInterval(() => {
      setFechaActual(new Date())
    }, 30000)
    return () => clearInterval(timer)
  }, [])

  const horaActual = fechaActual.toLocaleTimeString('es-CL', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  const fechaTexto = fechaActual.toLocaleDateString('es-CL', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).replace('.', '')
  const fechaDatos = `${fechaTexto}, ${horaActual}`

  useEffect(() => {
    let montado = true
    async function cargarEstablecimiento() {
      const centroResuelto = await establishmentService.resolverEstablecimiento(usuario)
      if (montado) {
        setEstablecimiento(centroResuelto)
        setCargandoCentro(false)
      }
    }
    cargarEstablecimiento()
    return () => { montado = false }
  }, [usuario])

  if (cargandoCentro) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-6 h-6 border-2 border-clinical-600 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-800">
      <Navbar
        usuario={usuario}
        establecimiento={establecimiento}
        onLogout={onLogout}
        tabActiva={tabActiva}
        onCambiarTab={setTabActiva}
      />
      
      <LiveStatusBar
        establecimiento={establecimiento}
        ultimaActualizacion={horaActual}
        tabActiva={tabActiva}
      />

      <main className="max-w-7xl w-full mx-auto px-4 sm:px-8 py-8 flex-1 space-y-10">
        {children ? (
          children
        ) : tabActiva === 'reportes' ? (
          /* SECCIÓN DE REPORTES (KPIs Semanales + Desglose Diario) */
          <ReportsSection establecimiento={establecimiento} />
        ) : (
          <div className="space-y-10">
            {/* SECCIÓN SUPERIOR: Métricas Clave en Vivo y Gráfico */}
            <DashboardSection establecimiento={establecimiento} />

            {/* SECCIÓN INFERIOR: Formulario de Triage + Tabla de Sesión */}
            <TriageSection establecimiento={establecimiento} />
          </div>
        )}
      </main>

      <Footer establecimiento={establecimiento} fechaDatos={fechaDatos} />
    </div>
  )
}