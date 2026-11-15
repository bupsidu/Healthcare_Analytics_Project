// frontend/src/components/ui/SelectField.jsx
import React from 'react'
import { ChevronDown } from 'lucide-react'

export default function SelectField({
  label,
  id,
  value,
  onChange,
  options = [],
  placeholder = 'Seleccione una opción',
  required = false,
  error,
}) {
  return (
    <div className="w-full font-sans">
      {label && (
        <label htmlFor={id} className="block text-xs font-semibold text-slate-700 mb-1.5">
          {label} {required && <span className="text-rose-500">*</span>}
        </label>
      )}
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={onChange}
          className={`w-full appearance-none pl-3.5 pr-10 py-2.5 text-sm bg-white border ${
            error ? 'border-rose-300 focus:border-rose-500' : 'border-slate-200 focus:border-clinical-600'
          } rounded-xl focus:outline-none focus:ring-2 focus:ring-clinical-100 transition text-slate-800 cursor-pointer`}
        >
          <option value="" disabled className="text-slate-400">
            {placeholder}
          </option>
          {options.map((opt) => (
            <option key={opt.value || opt} value={opt.value || opt} className="text-slate-800">
              {opt.label || opt}
            </option>
          ))}
        </select>
        <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-slate-400">
          <ChevronDown className="w-4 h-4" />
        </div>
      </div>
      {error && <p className="text-[11px] text-rose-500 mt-1">{error}</p>}
    </div>
  )
}