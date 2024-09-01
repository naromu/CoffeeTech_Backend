import asyncio
import httpx
import random
import string

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
    response = await client.post(API_URL, json=user_data)
    return response.status_code, response.json()

# Función principal para manejar múltiples registros simultáneamente
async def main():
    async with httpx.AsyncClient() as client:
        tasks = []
        for _ in range(1000):  # Simulamos 1000 usuarios
            user_data = generate_random_user()
            tasks.append(register_user(client, user_data))
        
        results = await asyncio.gather(*tasks)

        # Mostrar resultados
        success_count = sum(1 for status, _ in results if status == 200)
        failure_count = len(results) - success_count

        print(f"Total de registros exitosos: {success_count}")
        print(f"Total de registros fallidos: {failure_count}")

# Ejecutar la función principal
if __name__ == "__main__":
    asyncio.run(main())
