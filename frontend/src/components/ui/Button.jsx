//botón estándar con spinner y desactiva el botón por el doble click
import React from 'react'
import { Loader2 } from 'lucide-react'

export default function Button({
  children,
  type = 'button',
  variant = 'primary',
  isLoading = false,
  disabled = false,
  icon: Icon,
  className = '',
  onClick,
}) {
  const estilosBase = 'w-full py-3 px-4 font-medium text-sm rounded-xl transition flex items-center justify-center gap-2 focus:outline-none focus:ring-2 focus:ring-offset-2'

  const variantes = {
    primary: 'bg-clinical-600 hover:bg-clinical-700 text-white shadow-xs focus:ring-clinical-500 disabled:bg-slate-300',
    outline: 'border border-slate-200 text-slate-700 hover:bg-slate-50 focus:ring-slate-400',
    danger: 'bg-rose-600 hover:bg-rose-700 text-white focus:ring-rose-500',
  }

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || isLoading}
      className={`${estilosBase} ${variantes[variant]} ${className}`}
    >
      {isLoading ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin text-current" />
          <span>Verificando...</span>
        </>
      ) : (
        <>
          {Icon && <Icon className="w-4 h-4 shrink-0" />}
          <span>{children}</span>
        </>
      )}
    </button>
  )
}