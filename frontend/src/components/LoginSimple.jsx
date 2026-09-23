import React, { useState } from 'react';

export function LoginSimple() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mensaje, setMensaje] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setMensaje('Enviando credenciales al servidor FastAPI...');

    try {
      const response = await fetch('http://localhost:8000/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: new URLSearchParams({
          username: email,
          password: password,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setMensaje(`✅ Login exitoso. Token JWT: ${data.access_token.substring(0, 20)}...`);
        localStorage.setItem('token', data.access_token);
      } else {
        setMensaje(`❌ Error de Login: ${data.detail || 'Credenciales inválidas'}`);
      }
    } catch (error) {
      setMensaje('❌ Error de conexión: No se pudo conectar con http://localhost:8000');
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: '400px', border: '1px solid #cbd5e1', borderRadius: '8px', margin: '30px auto', fontFamily: 'sans-serif', background: '#ffffff' }}>
      <h3 style={{ marginTop: 0, color: '#0f172a' }}>Acceso Personal Médico</h3>
      
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '14px', textAlign: 'left' }}>
          <label style={{ fontSize: '14px', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Correo Electrónico:</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="medico@hospital.cl"
            required
            style={{ width: '100%', padding: '10px', borderRadius: '4px', border: '1px solid #94a3b8', boxSizing: 'border-box' }}
          />
        </div>

        <div style={{ marginBottom: '18px', textAlign: 'left' }}>
          <label style={{ fontSize: '14px', display: 'block', marginBottom: '4px', fontWeight: 'bold' }}>Contraseña:</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="******"
            required
            style={{ width: '100%', padding: '10px', borderRadius: '4px', border: '1px solid #94a3b8', boxSizing: 'border-box' }}
          />
        </div>

        <button type="submit" style={{ width: '100%', padding: '12px', backgroundColor: '#0284c7', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold', fontSize: '15px' }}>
          Iniciar Sesión
        </button>
      </form>

      {mensaje && (
        <div style={{ marginTop: '16px', fontSize: '13px', padding: '10px', background: '#f8fafc', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
          {mensaje}
        </div>
      )}
    </div>
  );
}
