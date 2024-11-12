from sqlalchemy import Column, Integer,BigInteger, String, Numeric, ForeignKey, DateTime, Boolean, Date, Sequence, Double, CheckConstraint, func 
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import pytz

Base = declarative_base()

def get_colombia_time():
    colombia_tz = pytz.timezone("America/Bogota")
    return datetime.now(colombia_tz)

# Modelo para Farm (Finca)

class Farm(Base):
    """
    Modelo de base de datos para representar una finca.

    Atributos:
    ----------
    farm_id : int
        Identificador único de la finca (clave primaria).
    name : str
        Nombre de la finca.
    area : Numeric
        Área de la finca.
    area_unit_id : int
        Unidad de medida del área (relación con UnitOfMeasure).
    status_id : int
        Estado actual de la finca (relación con Status).
    """
    __tablename__ = 'farm'

    farm_id = Column(Integer, primary_key=True, index=True, server_default=Sequence('farm_farm_id_seq').next_value())
    name = Column(String(100), nullable=False)
    area = Column(Numeric(10, 2), nullable=False)
    area_unit_id = Column(Integer, ForeignKey('unit_of_measure.unit_of_measure_id'), nullable=False)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=False)

    # Relaciones
    area_unit = relationship("UnitOfMeasure")
    status = relationship("Status")
    invitations = relationship("Invitation", back_populates="farm")
    user_roles_farms = relationship('UserRoleFarm', back_populates='farm')
    plots = relationship("Plot", back_populates="farm")


# Modelo para UserRoleFarm (relación entre usuarios, roles y fincas)
class UserRoleFarm(Base):
    """
    Relación entre usuarios, roles y fincas.

    Atributos:
    ----------
    user_role_farm_id : int
        Identificador único de la relación.
    role_id : int
        Identificador del rol (relación con Role).
    user_id : int
        Identificador del usuario (relación con User).
    farm_id : int
        Identificador de la finca (relación con Farm).
    status_id : int
        Estado actual de la relación.
    """
    __tablename__ = 'user_role_farm'

    user_role_farm_id = Column(Integer, primary_key=True, server_default=Sequence('user_role_farm_user_role_farm_id_seq').next_value())
    role_id = Column(Integer, ForeignKey('role.role_id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    farm_id = Column(Integer, ForeignKey('farm.farm_id'), nullable=False)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=False, default=22)

    # Relaciones
    user = relationship('User', back_populates='user_roles_farms')
    farm = relationship('Farm', back_populates='user_roles_farms')
    role = relationship('Role', back_populates='user_roles_farms')
    status = relationship('Status')


# Modelo para Role
class Role(Base):
    """
    Representa un rol que un usuario puede tener.

    Atributos:
    ----------
    role_id : int
        Identificador único del rol.
    name : str
        Nombre del rol (único).
    """
    __tablename__ = 'role'

    role_id = Column(Integer, primary_key=True, server_default=Sequence('role_role_id_seq').next_value())
    name = Column(String(50), nullable=False, unique=True)

    # Relación con RolePermission
    permissions = relationship("RolePermission", back_populates="role")
    user_roles_farms = relationship('UserRoleFarm', back_populates='role')


# Modelo para UnitOfMeasureType
class UnitOfMeasureType(Base):
    """
    Tipo de unidad de medida (ejemplo: área, volumen).

    Atributos:
    ----------
    unit_of_measure_type_id : int
        Identificador único del tipo de unidad.
    name : str
        Nombre del tipo de unidad.
    """
    __tablename__ = 'unit_of_measure_type'

    unit_of_measure_type_id = Column(Integer, primary_key=True, server_default=Sequence('unit_of_measure_type_unit_of_measure_type_id_seq').next_value())
    name = Column(String(50), nullable=False)

    # Relación con UnitOfMeasure
    units_of_measure = relationship("UnitOfMeasure", back_populates="unit_of_measure_type")


# Modelo para UnitOfMeasure
class UnitOfMeasure(Base):
    """
    Representa una unidad de medida (ejemplo: hectáreas, metros).

    Atributos:
    ----------
    unit_of_measure_id : int
        Identificador único de la unidad de medida.
    name : str
        Nombre de la unidad de medida.
    abbreviation : str
        Abreviación de la unidad de medida.
    unit_of_measure_type_id : int
        Relación con el tipo de unidad de medida.
    """
    __tablename__ = 'unit_of_measure'

    unit_of_measure_id = Column(Integer, primary_key=True, server_default=Sequence('unit_of_measure_unit_of_measure_id_seq').next_value())
    name = Column(String(50), nullable=False)
    abbreviation = Column(String(10), nullable=False)
    unit_of_measure_type_id = Column(Integer, ForeignKey('unit_of_measure_type.unit_of_measure_type_id'), nullable=False)

    # Relación con UnitOfMeasureType
    unit_of_measure_type = relationship("UnitOfMeasureType", back_populates="units_of_measure")


# Definición del modelo StatusType
class StatusType(Base):
    """
    Representa los tipos de estado de los registros.

    Atributos:
    ----------
    status_type_id : int
        Identificador único del tipo de estado.
    name : str
        Nombre del tipo de estado.
    """
    __tablename__ = 'status_type'

    status_type_id = Column(Integer, primary_key=True, server_default=Sequence('status_type_status_type_id_seq').next_value())
    name = Column(String(50), nullable=False)

    # Relación con Status
    statuses = relationship("Status", back_populates="status_type")


# Definición del modelo Status
class Status(Base):
    """
    Representa un estado de un registro (ejemplo: activo, inactivo).

    Atributos:
    ----------
    status_id : int
        Identificador único del estado.
    name : str
        Nombre del estado.
    status_type_id : int
        Relación con el tipo de estado.
    """
    __tablename__ = "status"

    status_id = Column(Integer, primary_key=True, server_default=Sequence('status_status_id_seq').next_value())
    name = Column(String(45), nullable=False)
    status_type_id = Column(Integer, ForeignKey("status_type.status_type_id"), nullable=False)

    # Relación con StatusType
    status_type = relationship("StatusType", back_populates="statuses")

    # Relación con User
    users = relationship("User", back_populates="status")
    
    # Relación con Notification
    notifications = relationship("Notification", back_populates="status")



# Definición del modelo User
class User(Base):
    """
    Representa un usuario en el sistema.

    Atributos:
    ----------
    user_id : int
        Identificador único del usuario.
    name : str
        Nombre del usuario.
    email : str
        Correo electrónico del usuario.
    password_hash : str
        Hash de la contraseña del usuario.
    verification_token : str
        Token de verificación del usuario.
    session_token : str
        Token de sesión del usuario.
    fcm_token : str
        Token de Firebase Cloud Messaging del usuario.
    status_id : int
        Relación con el estado del usuario.
    """
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True, server_default=Sequence('users_user_id_seq').next_value())
    name = Column(String(100), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    verification_token = Column(String(255), nullable=True)
    session_token = Column(String(50), nullable=True)
    fcm_token = Column(String(255), nullable=True)
    status_id = Column(Integer, ForeignKey("status.status_id"), nullable=False)

    # Relaciones
    status = relationship("Status", back_populates="users")
    user_roles_farms = relationship('UserRoleFarm', back_populates='user')
    notifications = relationship("Notification", foreign_keys="[Notification.user_id]", back_populates="user")


# Modelo para Permission
class Permission(Base):
    """
    Representa un permiso en el sistema.

    Atributos:
    ----------
    permission_id : int
        Identificador único del permiso.
    description : str
        Descripción del permiso.
    name : str
        Nombre del permiso.
    """

    __tablename__ = 'permission'

    permission_id = Column(Integer, primary_key=True, index=True, server_default=Sequence('permission_permission_id_seq').next_value())
    description = Column(String(200), nullable=False)
    name = Column(String(50), nullable=True, unique=True)

    # Relación con RolePermission
    roles = relationship("RolePermission", back_populates="permission")


# Modelo para RolePermission
class RolePermission(Base):
    """
    Representa la relación entre roles y permisos.

    Atributos:
    ----------
    role_id : int
        Identificador del rol.
    permission_id : int
        Identificador del permiso.
    """
    __tablename__ = 'role_permission'

    role_id = Column(Integer, ForeignKey('role.role_id'), primary_key=True, nullable=False)
    permission_id = Column(Integer, ForeignKey('permission.permission_id'), primary_key=True, nullable=False)

    # Relaciones con Role y Permission
    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")


# Modelo para Invitation
class Invitation(Base):
    """
    Representa una invitación para un usuario.

    Atributos:
    ----------
    invitation_id : int
        Identificador único de la invitación.
    email : str
        Correo electrónico del invitado.
    suggested_role : str
        Rol sugerido para el invitado.
    status_id : int
        Relación con el estado de la invitación.
    farm_id : int
        Relación con la finca a la que se invita.
    inviter_user_id : int
        Identificador del usuario que envía la invitación.
    date : datetime
        Fecha de creación de la invitación.
    """
    __tablename__ = 'invitation'

    invitation_id = Column(Integer, primary_key=True, server_default=Sequence('invitation_invitation_id_seq').next_value())
    email = Column(String(150), nullable=False)
    suggested_role = Column(String(50), nullable=False)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=False, default=24)
    farm_id = Column(Integer, ForeignKey('farm.farm_id'), nullable=False)
    inviter_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relaciones
    farm = relationship("Farm", back_populates="invitations")
    status = relationship("Status")
    inviter = relationship("User", foreign_keys=[inviter_user_id])
    notifications = relationship("Notification", back_populates="invitation")


# Modelo para NotificationType
class NotificationType(Base):
    """
    Representa el tipo de notificación.

    Atributos:
    ----------
    notification_type_id : int
        Identificador único del tipo de notificación.
    name : str
        Nombre del tipo de notificación.
    """
    __tablename__ = 'notification_type'

    notification_type_id = Column(Integer, primary_key=True, server_default=Sequence('notification_type_notification_type_id_seq').next_value())
    name = Column(String(50), nullable=False)

    # Relación con Notification
    notifications = relationship("Notification", back_populates="notification_type")


# Modelo para Notification
class Notification(Base):
    """
    Representa una notificación en el sistema.

    Atributos:
    ----------
    notifications_id : int
        Identificador único de la notificación.
    message : str
        Mensaje de la notificación.
    date : datetime
        Fecha de creación de la notificación.
    user_id : int
        Identificador del usuario que recibe la notificación.
    invitation_id : int
        Identificador de la invitación relacionada, si aplica.
    notification_type_id : int
        Tipo de notificación.
    farm_id : int
        Identificador de la finca relacionada, si aplica.
    status_id : int
        Relación con el estado de la notificación.
    """
    __tablename__ = 'notifications'

    notifications_id = Column(Integer, primary_key=True, server_default=Sequence('notifications_notifications_id_seq').next_value())
    message = Column(String(255), nullable=True)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    invitation_id = Column(Integer, ForeignKey('invitation.invitation_id'), nullable=True)
    notification_type_id = Column(Integer, ForeignKey('notification_type.notification_type_id'), nullable=True)
    farm_id = Column(Integer, ForeignKey('farm.farm_id'), nullable=True)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=True)


    # Relaciones
    user = relationship("User", foreign_keys=[user_id], back_populates="notifications")
    invitation = relationship("Invitation", back_populates="notifications")
    farm = relationship("Farm")
    notification_type = relationship("NotificationType", back_populates="notifications")
    
    # Agregar la relación con Status
    status = relationship("Status", back_populates="notifications")



# Modelo para Plot
class Plot(Base):
    """
    Representa un lote de cultivo en una finca.

    Atributos:
    ----------
    plot_id : int
        Identificador único del lote.
    name : str
        Nombre del lote.
    longitude : str
        Longitud del lote.
    latitude : str
        Latitud del lote.
    altitude : str
        Altitud del lote.
    coffee_variety_id : int
        Relación con la variedad de café plantada en el lote.
    farm_id : int
        Relación con la finca a la que pertenece el lote.
    status_id : int
        Relación con el estado del lote.
    """
    __tablename__ = 'plot'

    plot_id = Column(Integer, primary_key=True, index=True, server_default=Sequence('plot_plot_id_seq').next_value())
    name = Column(String(100), nullable=False)
    longitude = Column(String(45), nullable=True)
    latitude = Column(String(45), nullable=True)
    altitude = Column(String(45), nullable=True)
    coffee_variety_id = Column(Integer, ForeignKey('coffee_variety.coffee_variety_id'), nullable=False)
    farm_id = Column(Integer, ForeignKey('farm.farm_id'), nullable=False)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=True)

    # Relaciones
    farm = relationship("Farm", back_populates="plots")
    coffee_variety = relationship("CoffeeVariety", back_populates="plots")

    cultural_work_tasks = relationship("CulturalWorkTask", back_populates="plot")

# Modelo actualizado para CoffeeVariety
class CoffeeVariety(Base):
    """
    Representa una variedad de café con los atributos mínimos necesarios.

    Atributos:
    ----------
    coffee_variety_id : int
        Identificador único de la variedad de café.
    name : str
        Nombre de la variedad de café.
    """
    __tablename__ = 'coffee_variety'

    coffee_variety_id = Column(Integer, primary_key=True, index=True, server_default="nextval('coffee_variety_coffee_variety_id_seq')")
    name = Column(String(50), nullable=False)

    # Relaciones
    plots = relationship("Plot", back_populates="coffee_variety")


# Modelo para FloweringType (Tipo de Floración)
class FloweringType(Base):
    """
    Representa un tipo de floración en el sistema.

    Atributos:
    ----------
    flowering_type_id : int
        Identificador único del tipo de floración.
    name : str
        Nombre del tipo de floración.
    """
    __tablename__ = 'flowering_type'

    flowering_type_id = Column(Integer, primary_key=True, server_default=Sequence('flowering_type_flowering_type_id_seq').next_value())
    name = Column(String(50), nullable=False)

    # Relación con Flowering
    flowerings = relationship("Flowering", back_populates="flowering_type")


# Modelo para Flowering (Floración)
class Flowering(Base):
    """
    Representa un evento de floración en un lote de cultivo.

    Atributos:
    ----------
    flowering_id : int
        Identificador único de la floración.
    plot_id : int
        Relación con el lote en el que ocurre la floración.
    flowering_date : date
        Fecha de la floración.
    harvest_date : date
        Fecha de la cosecha, si aplica.
    status_id : int
        Relación con el estado de la floración.
    flowering_type_id : int
        Relación con el tipo de floración.
    """
    __tablename__ = 'flowering'

    flowering_id = Column(Integer, primary_key=True, server_default=Sequence('flowering_flowering_id_seq').next_value())
    plot_id = Column(Integer, ForeignKey('plot.plot_id'), nullable=False)
    flowering_date = Column(Date, nullable=False)
    harvest_date = Column(Date, nullable=True)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=False)
    flowering_type_id = Column(Integer, ForeignKey('flowering_type.flowering_type_id'), nullable=False)

    # Relaciones
    plot = relationship("Plot")
    status = relationship("Status")
    flowering_type = relationship("FloweringType", back_populates="flowerings")
    
    
class CulturalWork(Base):
    """
    Representa una tarea de labor cultural.

    Atributos:
    ----------
    cultural_works_id : int
        Identificador único de la tarea de labor cultural.
    name : str
        Nombre de la tarea de labor cultural.
    description : str
        Descripción de la tarea de labor cultural.
    """
    __tablename__ = 'cultural_works'

    cultural_works_id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)

    # Relación con las tareas específicas asignadas a un lote
    cultural_work_tasks = relationship("CulturalWorkTask", back_populates="cultural_work")
    
    

class CulturalWorkTask(Base):
    """
    Representa una tarea de labor cultural asignada a un lote.
    """
    __tablename__ = 'cultural_work_tasks'

    cultural_work_tasks_id = Column(Integer, primary_key=True, autoincrement=True)
    cultural_works_id = Column(Integer, ForeignKey('cultural_works.cultural_works_id'), nullable=False)
    plot_id = Column(Integer, ForeignKey('plot.plot_id'), nullable=False)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=True)
    reminder_owner = Column(Boolean, nullable=False, default=False)
    reminder_collaborator = Column(Boolean, nullable=False, default=False)
    collaborator_user_id = Column(Integer, nullable=False)
    owner_user_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=get_colombia_time)
    task_date = Column(Date, nullable=True)

    # Relaciones
    cultural_work = relationship("CulturalWork", back_populates="cultural_work_tasks")
    plot = relationship("Plot", back_populates="cultural_work_tasks")
    status = relationship("Status")
    health_checks = relationship("HealthCheck", back_populates="cultural_work_task")

class HealthCheck(Base):
    __tablename__ = 'health_checks'

    health_checks_id = Column(Integer, primary_key=True, index=True, server_default=Sequence('health_checks_id_seq').next_value())
    check_date = Column(Date, nullable=False, default=datetime.utcnow)
    recommendation_id = Column(Integer, ForeignKey('recommendation.recommendation_id'), nullable=False)
    prediction = Column(String(50), nullable=False)
    cultural_work_tasks_id = Column(Integer, ForeignKey('cultural_work_tasks.cultural_work_tasks_id'), nullable=False)
    
    # Nueva columna status_id con clave foránea a la tabla status
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=False, default=35)

    # Relaciones
    recommendation = relationship("Recommendation", back_populates="health_checks")
    cultural_work_task = relationship("CulturalWorkTask", back_populates="health_checks")
    status = relationship("Status")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.status_id:
            # Asigna el status_id predeterminado si no se proporciona
            self.status_id = 35  # 'pendiente_deteccion'

    
class Recommendation(Base):
    __tablename__ = 'recommendation'

    recommendation_id = Column(Integer, primary_key=True, index=True)  # Cambié a SERIAL si es necesario
    recommendation = Column(String(255), nullable=False)
    name = Column(String(45), nullable=False)

    # Relaciones
    health_checks = relationship("HealthCheck", back_populates="recommendation")# Asegúrate de que exista la relación en el modelo HealthCheck
     
    
    
# Modelo para TransactionCategory
class TransactionCategory(Base):
    """
    Representa una categoría de transacción en el sistema.

    Atributos:
    ----------
    transaction_category_id : int
        Identificador único de la categoría de transacción.
    name : str
        Nombre de la categoría de transacción.
    transaction_type_id : int
        Relación con el tipo de transacción.
    """
    __tablename__ = 'transaction_category'

    transaction_category_id = Column(Integer, primary_key=True, server_default=Sequence('transaction_category_transaction_category_id_seq').next_value())
    name = Column(String(50), nullable=False)
    transaction_type_id = Column(Integer, ForeignKey('transaction_type.transaction_type_id'), nullable=False)

    # Relaciones
    transaction_type = relationship("TransactionType", back_populates="categories")
    transactions = relationship("Transaction", back_populates="transaction_category")  # Relación inversa


    # Modelo para TransactionType
class TransactionType(Base):
    """
    Representa un tipo de transacción en el sistema.

    Atributos:
    ----------
    transaction_type_id : int
        Identificador único del tipo de transacción.
    name : str
        Nombre del tipo de transacción.
    """
    __tablename__ = 'transaction_type'

    transaction_type_id = Column(Integer, primary_key=True, server_default=Sequence('transaction_type_transaction_type_id_seq').next_value())
    name = Column(String(50), nullable=False)

    # Relaciones
    categories = relationship("TransactionCategory", back_populates="transaction_type")
    transactions = relationship("Transaction", back_populates="transaction_type")
    
    
    # Modelo para Transaction
class Transaction(Base):
    """
    Representa una transacción en un lote de cultivo.

    Atributos:
    ----------
    transaction_id : int
        Identificador único de la transacción.
    plot_id : int
        Relación con el lote en el que ocurre la transacción.
    description : str
        Descripción de la transacción.
    transaction_type_id : int
        Relación con el tipo de transacción.
    transaction_category_id : int
        Relación con la categoría de la transacción.
    transaction_date : date
        Fecha de la transacción.
    status_id : int
        Relación con el estado de la transacción.
    value : Numeric
        Valor de la transacción.
    """
    __tablename__ = 'transaction'

    transaction_id = Column(Integer, primary_key=True, server_default=Sequence('transaction_transaction_id_seq').next_value())
    plot_id = Column(Integer, ForeignKey('plot.plot_id'), nullable=False)
    description = Column(String(50), nullable=True)
    transaction_type_id = Column(Integer, ForeignKey('transaction_type.transaction_type_id'), nullable=False)
    transaction_category_id = Column(Integer, ForeignKey('transaction_category.transaction_category_id'), nullable=False)
    transaction_date = Column(Date, nullable=False)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=False)
    value = Column(BigInteger, nullable=False)
    creador_id = Column(Integer, nullable=False)  # Nueva columna con valor predeterminado 2


    # Relaciones
    plot = relationship("Plot")
    transaction_type = relationship("TransactionType", back_populates="transactions")
    transaction_category = relationship("TransactionCategory")
    status = relationship("Status")
