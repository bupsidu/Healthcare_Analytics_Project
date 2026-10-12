import urllib.request
import json
import csv
import os

# Coordenadas de las principales capitales regionales de Chile
regiones_coords = {
    'Arica y Parinacota': {'lat': -18.47, 'lon': -70.31},
    'Tarapaca': {'lat': -20.21, 'lon': -70.15},
    'Antofagasta': {'lat': -23.65, 'lon': -70.40},
    'Atacama': {'lat': -27.36, 'lon': -70.33},
    'Coquimbo': {'lat': -29.90, 'lon': -71.25},
    'Valparaiso': {'lat': -33.04, 'lon': -71.61},
    'Metropolitana': {'lat': -33.45, 'lon': -70.66},
    'OHiggins': {'lat': -34.17, 'lon': -70.74},
    'Maule': {'lat': -35.42, 'lon': -71.65},
    'Nuble': {'lat': -36.60, 'lon': -72.10},
    'Biobio': {'lat': -36.82, 'lon': -73.04},
    'Araucania': {'lat': -38.73, 'lon': -72.59},
    'Los Rios': {'lat': -39.81, 'lon': -73.24},
    'Los Lagos': {'lat': -41.47, 'lon': -72.94},
    'Aysen': {'lat': -45.57, 'lon': -72.06},
    'Magallanes': {'lat': -53.16, 'lon': -70.91}
}

# Guardar directamente en el Escritorio
escritorio = os.path.expanduser('~/Desktop')
nombre_archivo = os.path.join(escritorio, 'Contaminacion 2024 y 2025.csv')

print("Descargando datos de contaminación (MP2.5 y MP10) 2024-2025...")

with open(nombre_archivo, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    # Encabezados del archivo
    writer.writerow(['Fecha', 'MP2_5', 'MP10', 'Region'])

    for region, coords in regiones_coords.items():
        print(f"Descargando región: {region}...")
        url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={coords['lat']}&longitude={coords['lon']}&start_date=2024-01-01&end_date=2025-12-31&hourly=pm2_5,pm10&timezone=auto"
        
        try:
            req = urllib.request.urlopen(url)
            data = json.loads(req.read().decode('utf-8'))
            
            times = data['hourly']['time']
            pm25_list = data['hourly']['pm2_5']
            pm10_list = data['hourly']['pm10']
            
            # Agrupar por días (24 horas por día)
            diarios = {}
            for t, p25, p10 in zip(times, pm25_list, pm10_list):
                fecha = t.split('T')[0] # Extraer YYYY-MM-DD
                
                if fecha not in diarios:
                    diarios[fecha] = {'pm25': [], 'pm10': []}
                
                if p25 is not None: diarios[fecha]['pm25'].append(p25)
                if p10 is not None: diarios[fecha]['pm10'].append(p10)
            
            # Escribir el promedio diario
            for fecha, valores in diarios.items():
                avg_pm25 = round(sum(valores['pm25']) / len(valores['pm25']), 2) if valores['pm25'] else 0.0
                avg_pm10 = round(sum(valores['pm10']) / len(valores['pm10']), 2) if valores['pm10'] else 0.0
                writer.writerow([fecha, avg_pm25, avg_pm10, region])
                
        except Exception as e:
            print(f"Error procesando {region}: {e}")

print(f"\n✅ ¡Descarga completada con éxito!")
print(f"Se creó el archivo en tu Escritorio: {nombre_archivo}")