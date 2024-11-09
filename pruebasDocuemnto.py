import base64
import requests
import concurrent.futures
import time
import random

# Endpoint y token de sesión
url = "https://prueba-production-1b78.up.railway.app/detection/detectdisease_and_deficiency"
session_token = "g5KhrbOMewfdnzb0XdagZme2rqRTtW7Q"
cultural_work_tasks_id = 57  # Reemplaza con el ID correspondiente

# Cargar la imagen una vez para reutilizarla en cada petición
def convertir_imagen_a_base64(ruta):
    with open(ruta, "rb") as imagen:
        return base64.b64encode(imagen.read()).decode("utf-8")

# Ruta de la imagen que deseas enviar
ruta_imagen = "ferrogum.jpeg"

# Convertir la imagen a base64
imagen_base64 = convertir_imagen_a_base64(ruta_imagen)

# Función que crea el payload con 1 o 10 imágenes
def crear_payload():
    # Decidir aleatoriamente si el payload tendrá 1 o 10 imágenes
    num_imagenes = random.randint(1, 10)
    payload = {
        "session_token": session_token,
        "cultural_work_tasks_id": cultural_work_tasks_id,
        "images": [{"image_base64": imagen_base64} for _ in range(num_imagenes)]
    }
    print(f"Enviando payload con {num_imagenes} imágenes")
    return payload

# Función para enviar la petición y medir el tiempo de respuesta
def enviar_peticion():
    payload = crear_payload()  # Generar el payload con 1 o 10 imágenes
    
    try:
        inicio = time.time()
        respuesta = requests.post(url, json=payload)
        tiempo_respuesta = time.time() - inicio
        
        if respuesta.status_code == 200:
            print(f"Petición exitosa en {tiempo_respuesta:.2f} segundos")
            return tiempo_respuesta
        else:
            print(f"Error: {respuesta.status_code} - {respuesta.text}")
            return None
    except Exception as e:
        print(f"Error al procesar la petición: {e}")
        return None

# Configuración de la prueba de carga
num_peticion_concurrentes = 50  # Número de peticiones simultáneas
resultados = []

# Ejecutar la prueba de carga
print(f"Iniciando prueba de carga con {num_peticion_concurrentes} peticiones simultáneas...")
inicio_total = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=num_peticion_concurrentes) as executor:
    # Lanza todas las peticiones de carga
    futures = [executor.submit(enviar_peticion) for _ in range(num_peticion_concurrentes)]
    
    # Espera a que todas las peticiones finalicen y recoge los resultados
    for future in concurrent.futures.as_completed(futures):
        tiempo_respuesta = future.result()
        if tiempo_respuesta:
            resultados.append(tiempo_respuesta)

# Medir el tiempo total de la prueba de carga
tiempo_total = time.time() - inicio_total
print(f"Prueba de carga completada en {tiempo_total:.2f} segundos")
print(f"Tiempo promedio de respuesta: {sum(resultados) / len(resultados):.2f} segundos")
print(f"Respuestas exitosas: {len(resultados)} de {num_peticion_concurrentes}")
