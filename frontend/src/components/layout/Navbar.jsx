// frontend/src/components/layout/Navbar.jsx
import React from 'react'
import { Hospital, User, LogOut } from 'lucide-react'

export default function Navbar({ usuario, establecimiento, onLogout }) {
  return (
    <header className="w-full bg-white border-b border-slate-200/80 sticky top-0 z-30 font-sans">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 h-16 flex items-center justify-between gap-4">
        
        {/* Logo y Nombre Dinámico del Hospital */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-clinical-600 flex items-center justify-center text-white shadow-xs">
            <Hospital className="w-5 h-5" />
          </div>
          <div className="leading-tight">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-slate-900 tracking-tight">HealthCare Analytics</span>
              <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-clinical-50 text-clinical-700 border border-clinical-200/60">
                {establecimiento?.tipo || 'Centro'}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Project · <span className="font-medium text-slate-700">{establecimiento?.nombre || 'Centro de Salud'}</span>
            </p>
          </div>
        </div>

        {/* Pestañas de Navegación (Sin Configuración) */}
        <nav className="hidden md:flex items-center gap-1 bg-slate-50/80 p-1 rounded-xl border border-slate-200/60">
          <span className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-clinical-100 text-clinical-800 shadow-2xs">
            Dashboard & Triage
          </span>
          <button
            type="button"
            onClick={() => alert('Módulo de reportes epidemiológicos MINSAL.')}
            className="px-4 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 rounded-lg cursor-pointer transition"
          >
            Reportes
          </button>
        </nav>

        {/* Perfil del Usuario y Cerrar Sesión */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 pl-2">
            <div className="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 border border-slate-200">
              <User className="w-4 h-4" />
            </div>
            <span className="hidden sm:inline text-xs font-medium text-slate-700 font-mono">
              {usuario?.email || 'usuario@hospital.cl'}
            </span>
          </div>

          <div className="h-4 w-px bg-slate-200" />

          <button
            type="button"
            onClick={onLogout}
            title="Cerrar sesión segura"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-rose-600 transition-colors cursor-pointer px-2 py-1 rounded-lg hover:bg-rose-50"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Cerrar sesión</span>
          </button>
        </div>

      </div>
    </header>
  )
}