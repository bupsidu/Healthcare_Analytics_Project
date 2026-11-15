// frontend/src/components/layout/LiveStatusBar.jsx
import React from 'react'
import { Calendar } from 'lucide-react'

export default function LiveStatusBar({
  establecimiento,
  ultimaActualizacion = '08:42',
}) {
  return (
    <div className="w-full bg-white border-b border-slate-200/60 py-5 font-sans">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        
        <div>
          <div className="flex items-center gap-2 text-[11px] font-bold text-slate-400 tracking-wider uppercase mb-1">
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span>EN VIVO</span>
            <span>·</span>
            <span>ACTUALIZADO {ultimaActualizacion}</span>
          </div>

          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Dashboard de Demanda — {establecimiento?.nombre || 'Centro de Salud'}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Predicción de afluencia basada en variables climáticas y epidemiológicas
          </p>
        </div>

        {/* Indicador de Vista: Semanal (Fijo según regla de negocio, sin toggle mensual) */}
        <div className="inline-flex items-center gap-2 self-start md:self-auto px-3.5 py-1.5 rounded-xl bg-slate-100 border border-slate-200/80 text-xs font-semibold text-slate-700 shadow-2xs">
          <Calendar className="w-3.5 h-3.5 text-clinical-600" />
          <span>Vista Semanal</span>
        </div>

      </div>
    </div>
  )
}