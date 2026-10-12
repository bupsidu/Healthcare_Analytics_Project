/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Paleta de colores clínica (los verdes de los botones de Figma)
        clinical: {
          50: '#f0fdfa',
          100: '#ccfbf1',
          200: '#99f6e4',
          500: '#14b8a6',
          600: '#0d9488', // Color de acción ("Iniciar Sesión", "Registrar consulta")
          700: '#0f766e',
          800: '#115e59',
          900: '#134e4a',
        },
        // Semáforo de alerta hospitalaria
        status: {
          success: '#10b981', // Verde: Estado normal / Capacidad adecuada
          warning: '#f59e0b', // Amarillo: Alerta moderada 
          danger: '#ef4444',  // Rojo: Alerta crítica / Saturación hospitalaria
        }
      }
    },
  },
  plugins: [],
}

