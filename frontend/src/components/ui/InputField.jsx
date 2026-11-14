// diseño label + input con icono y validación de errores
import React, { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

export default function InputField({
  label,
  id,
  type = 'text',
  value,
  onChange,
  placeholder,
  required = false,
  icon: Icon,
  isPassword = false,
  error,
}) {
  const [mostrarPassword, setMostrarPassword] = useState(false)
  const tipoInputEfectivo = isPassword ? (mostrarPassword ? 'text' : 'password') : type

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={id} className="block text-xs font-semibold text-slate-700 mb-1.5">
          {label} {required && <span className="text-rose-500">*</span>}
        </label>
      )}
      <div className="relative">
        {Icon && (
          <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
            <Icon className="w-4 h-4" />
          </div>
        )}

        <input
          id={id}
          type={tipoInputEfectivo}
          required={required}
          value={value}
          onChange={onChange}
          placeholder={placeholder}
          className={`w-full ${Icon ? 'pl-10' : 'pl-3.5'} ${
            isPassword ? 'pr-10' : 'pr-3.5'
          } py-2.5 text-sm bg-white border ${
            error ? 'border-rose-300 focus:border-rose-500' : 'border-slate-200 focus:border-clinical-600'
          } rounded-xl focus:outline-none focus:ring-2 focus:ring-clinical-100 transition`}
        />

        {isPassword && (
          <button
            type="button"
            onClick={() => setMostrarPassword(!mostrarPassword)}
            className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600"
            tabIndex={-1}
          >
            {mostrarPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        )}
      </div>
      {error && <p className="text-[11px] text-rose-500 mt-1">{error}</p>}
    </div>
  )
}