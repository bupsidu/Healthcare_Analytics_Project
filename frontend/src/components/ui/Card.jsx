// Contenedor blanco con bordes redondeados
import React from 'react'

export default function Card({ children, className = '' }) {
  return (
    <div className={`bg-white border border-slate-200/90 rounded-3xl p-8 sm:p-10 shadow-sm ${className}`}>
      {children}
    </div>
  )
}