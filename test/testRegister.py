import asyncio
import httpx
import random
import string
import time

# URL de la API para la ruta /register
API_URL = "http://localhost:8000/register"

# Generador de emails y contraseñas aleatorios para los usuarios
def generate_random_user():
    name = ''.join(random.choices(string.ascii_letters, k=8))
    email = f"{name.lower()}@example.com"
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    return {
        "name": name,
        "email": email,
        "password": password,
        "passwordConfirmation": password
    }

# Función para realizar la petición de registro
async def register_user(client, user_data):
    try:
        response = await client.post(API_URL, json=user_data)
        return response.status_code, response.json()
    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        return None, None

# Función principal para manejar múltiples registros simultáneamente
async def main():
    async with httpx.AsyncClient() as client:
        tasks = []
        max_concurrent_requests = 100  # Limitar el número de solicitudes concurrentes
        for i in range(1000):  # Simulamos 1000 usuarios
            user_data = generate_random_user()
            tasks.append(register_user(client, user_data))
            max_concurrent_requests = 50  # o un número aún más bajo

            if (i + 1) % max_concurrent_requests == 0:  # Enviar en lotes de tamaño max_concurrent_requests
                results = await asyncio.gather(*tasks)
                tasks = []  # Limpiar la lista de tareas para el siguiente lote

                # Mostrar resultados del lote actual
                success_count = sum(1 for status, _ in results if status == 200)
                failure_count = len(results) - success_count
                print(f"Lote {i // max_concurrent_requests + 1}: {success_count} exitosos, {failure_count} fallidos")

        # Enviar cualquier tarea restante
        if tasks:
            results = await asyncio.gather(*tasks)
            success_count = sum(1 for status, _ in results if status == 200)
            failure_count = len(results) - success_count
            print(f"Último lote: {success_count} exitosos, {failure_count} fallidos")

# Ejecutar la función principal
if __name__ == "__main__":
    asyncio.run(main())
