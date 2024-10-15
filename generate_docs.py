import os
import subprocess

# Lista de archivos permitidos
allowed_files = [
    'main.py', 'auth.py', 'collaborators.py', 'farm.py', 
    'flowering.py', 'invitation.py', 'notification.py', 
    'plots.py', 'utils.py', 'models.py', 'email.py', 
    'FCM.py', 'response.py', 'security.py', 'status.py', 
    'dataBase.py'
]

def is_allowed_module(module_path, base_dir):
    """Verifica si el módulo se encuentra en la lista de archivos permitidos."""
    relative_path = os.path.relpath(module_path, base_dir)  # Obtener la ruta relativa al directorio base
    
    # Comprobar si el archivo está en la lista permitida
    for allowed_file in allowed_files:
        if relative_path.endswith(allowed_file):  
            return True
    return False

def generate_docs_for_selected_modules(base_dir, output_file):
    """Genera la documentación solo para los módulos permitidos."""
    with open(output_file, 'w', encoding='utf-8') as doc_file:
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file.endswith('.py'):
                    module_path = os.path.join(root, file)
                    if is_allowed_module(module_path, base_dir):  # Verifica si el módulo está permitido
                        # Formatea el módulo para pydoc
                        module = module_path.replace(base_dir + os.sep, '').replace(os.sep, '.').replace('.py', '')
                        try:
                            # Genera la documentación usando pydoc
                            output = subprocess.check_output(['python', '-m', 'pydoc', module], stderr=subprocess.STDOUT)
                            try:
                                doc_file.write(output.decode('utf-8'))
                            except UnicodeDecodeError:
                                doc_file.write(output.decode('latin-1'))
                            doc_file.write("\n" + "="*80 + "\n")  # Separador entre módulos
                            print(f"Documentación generada para el módulo: {module}")
                        except subprocess.CalledProcessError as e:
                            print(f"Error al generar documentación para el módulo: {module}. Error: {e.output.decode('utf-8')}")

if __name__ == '__main__':
    base_directory = 'C:/Users/sebas/OneDrive/Escritorio/caffee/CoffeeTech_Backend'  # Cambia esto por la ruta a tu proyecto
    output_document = 'documentacion_seleccionada.txt'
    generate_docs_for_selected_modules(base_directory, output_document)
    print("Documentación generada con éxito.")
