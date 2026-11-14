// frontend/src/components/layout/Footer.jsx
import React from 'react'

export default function Footer({
  establecimiento,
  version = 'v1.0.0',
  fechaDatos = '',
}) {
  return (
    <footer className="w-full border-t border-slate-200/80 bg-white py-4 font-sans text-xs text-slate-400 mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-8 flex flex-col sm:flex-row items-center justify-between gap-2">
        <p>
          HealthCare Analytics Project · <span className="font-medium text-slate-600">{establecimiento?.nombre || 'Centro de Salud'}</span> · <span className="font-mono">{version}</span>
        </p>
        <p>
          Datos actualizados: <span className="font-medium text-slate-600">{fechaDatos}</span>
        </p>
      </div>
    </footer>
  )
}