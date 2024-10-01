from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, CheckConstraint, DateTime, Boolean, Date, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from sqlalchemy.orm import registry

mapper_registry = registry()
mapper_registry.configure()

Base = declarative_base()

# Modelo para Farm (Finca)
class Farm(Base):
    __tablename__ = 'farm'

    farm_id = Column(Integer, primary_key=True, index=True)
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
    __tablename__ = 'user_role_farm'

    user_role_farm_id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey('role.role_id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    farm_id = Column(Integer, ForeignKey('farm.farm_id'), nullable=False)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=False, default=22)  # Nuevo campo status_id
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=False, default=22)  # Nuevo campo status_id

    # Relaciones
    user = relationship('User', back_populates='user_roles_farms')
    farm = relationship('Farm', back_populates='user_roles_farms')
    role = relationship('Role', back_populates='user_roles_farms')
    status = relationship('Status')  # Relación con la tabla 'Status'



# Modelo para Role
class Role(Base):
    __tablename__ = 'role'

    role_id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    
     # Relación con RolePermission (permisos asociados a este rol)
    permissions = relationship("RolePermission", back_populates="role")
    user_roles_farms = relationship('UserRoleFarm', back_populates='role')

# Modelo para UnitOfMeasureType
class UnitOfMeasureType(Base):
    __tablename__ = 'unit_of_measure_type'

    unit_of_measure_type_id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)

    # Relación con UnitOfMeasure
    units_of_measure = relationship("UnitOfMeasure", back_populates="unit_of_measure_type")

# Modelo para UnitOfMeasure
class UnitOfMeasure(Base):
    __tablename__ = 'unit_of_measure'

    unit_of_measure_id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    abbreviation = Column(String(10), nullable=False)
    unit_of_measure_type_id = Column(Integer, ForeignKey('unit_of_measure_type.unit_of_measure_type_id'), nullable=False)

    # Relación con UnitOfMeasureType
    unit_of_measure_type = relationship("UnitOfMeasureType", back_populates="units_of_measure")


# Definición del modelo StatusType
class StatusType(Base):
    __tablename__ = 'status_type'

    status_type_id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)

    # Relación con Status
    statuses = relationship("Status", back_populates="status_type")


# Definición del modelo Status
class Status(Base):
    __tablename__ = "status"

    status_id = Column(Integer, primary_key=True)
    name = Column(String(45), nullable=False)
    description = Column(String(255), nullable=True)
    status_type_id = Column(Integer, ForeignKey("status_type.status_type_id"), nullable=False)

    # Relación con StatusType
    status_type = relationship("StatusType", back_populates="statuses")

    # Relación con User (usando una cadena para resolver el nombre de la clase)
    users = relationship("User", back_populates="status")


# Definición del modelo User
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), nullable=False, unique=True)
    password_hash = Column(String(60), nullable=False)
    verification_token = Column(String(50), nullable=True)
    session_token = Column(String(50), nullable=True)
    fcm_token = Column(String(255), nullable=True)  # Agregar el campo FCM token
    status_id = Column(Integer, ForeignKey("status.status_id"), nullable=False)

    # Relaciones
    status = relationship("Status", back_populates="users")
    user_roles_farms = relationship('UserRoleFarm', back_populates='user') 
    notifications = relationship("Notification", foreign_keys="[Notification.user_id]", back_populates="user")



# Modelo para Permission
class Permission(Base):
    __tablename__ = 'permission'

    permission_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    description = Column(String(200), nullable=False)
    name = Column(String(50), nullable=True, unique=True)

    # Relación con RolePermission (roles asociados a este permiso)
    roles = relationship("RolePermission", back_populates="permission")


# Modelo para RolePermission (relación entre roles y permisos)
class RolePermission(Base):
    __tablename__ = 'role_permission'

    role_id = Column(Integer, ForeignKey('role.role_id'), primary_key=True, nullable=False)
    permission_id = Column(Integer, ForeignKey('permission.permission_id'), primary_key=True, nullable=False)

    # Relaciones con Role y Permission
    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")
    
# Modelo para Invitation (Invitación)
# Modelo para Invitation (Invitación)
class Invitation(Base):
    __tablename__ = 'invitation'

    invitation_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(150), nullable=False)
    suggested_role = Column(String(50), nullable=False)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=False, default=24)
    farm_id = Column(Integer, ForeignKey('farm.farm_id'), nullable=False)
    inviter_user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)  # Nuevo campo para el invitador
    date = Column(DateTime, default=datetime.utcnow, nullable=False)  # Fecha de creación

    # Relaciones
    farm = relationship("Farm", back_populates="invitations")
    status = relationship("Status")
    inviter = relationship("User", foreign_keys=[inviter_user_id])  # Relación con el invitador
    notifications = relationship("Notification", back_populates="invitation")


# Modelo para NotificationType (Tipos de notificaciones)
class NotificationType(Base):
    __tablename__ = 'notification_type'

    notification_type_id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)

    # Relación con Notification
    notifications = relationship("Notification", back_populates="notification_type")
    

# Modelo para Notification (Notificaciones)
class Notification(Base):
    __tablename__ = 'notifications'

    notifications_id = Column(Integer, primary_key=True, autoincrement=True)
    message = Column(String(255), nullable=True)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    invitation_id = Column(Integer, ForeignKey('invitation.invitation_id'), nullable=True)
    farm_id = Column(Integer, ForeignKey('farm.farm_id'), nullable=True)
    notification_type_id = Column(Integer, ForeignKey('notification_type.notification_type_id'), nullable=True)  # Nueva clave foránea
    reminder_time = Column(DateTime, nullable=True)
    status_id = Column(Integer, ForeignKey('status.status_id'), nullable=True)  # Nueva clave foránea

    # Relaciones
    user = relationship("User", foreign_keys=[user_id], back_populates="notifications")
    invitation = relationship("Invitation", back_populates="notifications")
    farm = relationship("Farm")
    notification_type = relationship("NotificationType", back_populates="notifications")  # Relación con NotificationType

class Plot(Base):
    __tablename__ = 'plot'

    plot_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    seed_time = Column(Date, nullable=True)
    longitude = Column(String(45), nullable=True)
    latitude = Column(String(45), nullable=True)
    altitude = Column(String(45), nullable=True)
    coffee_variety_id = Column(Integer, ForeignKey('coffee_variety.coffee_variety_id'), nullable=False)
    farm_id = Column(Integer, ForeignKey('farm.farm_id'), nullable=False)

    # Relaciones
    plot_phases = relationship('PlotPhase', back_populates='plot')
    farm = relationship("Farm", back_populates="plots")
    
    coffee_variety = relationship("CoffeeVariety", back_populates="plots")

    
class Phase(Base):
    __tablename__ = 'phase'

    phase_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    date = Column(Date, nullable=True)

    # Relaciones
    plot_phases = relationship('PlotPhase', back_populates='phase')
    
class PlotPhase(Base):
    __tablename__ = 'plot_phases'

    plot_phase_id = Column(Integer, primary_key=True, index=True)
    phase_id = Column(Integer, ForeignKey('phase.phase_id'), nullable=False)
    plot_id = Column(Integer, ForeignKey('plot.plot_id'), nullable=False)

    # Relaciones
    phase = relationship('Phase', back_populates='plot_phases')
    plot = relationship('Plot', back_populates='plot_phases')

class CoffeeVariety(Base):
    __tablename__ = 'coffee_variety'
    
    coffee_variety_id = Column(Integer, primary_key=True, index=True, nullable=False)
    name = Column(String(50), nullable=False)
    description = Column(String(255), default=None)
    rust_resistant = Column(Boolean, nullable=False)
    growth_habit = Column(String(50), nullable=False)
    plant_density_sun = Column(DECIMAL(10, 2), default=None)
    plant_density_shade = Column(DECIMAL(10, 2), default=None)
    production = Column(DECIMAL(10, 2), default=None)
    altitude_min = Column(Integer, default=None)
    altitude_max = Column(Integer, default=None)
    plant_density_unit_id = Column(Integer, ForeignKey('unit_of_measure.unit_of_measure_id'), nullable=False)
    production_unit_id = Column(Integer, ForeignKey('unit_of_measure.unit_of_measure_id'), nullable=False)
    altitude_unit_id = Column(Integer, ForeignKey('unit_of_measure.unit_of_measure_id'), nullable=False)

    # Relaciones
    plots = relationship("Plot", back_populates="coffee_variety")

    def __repr__(self):
        return (f"<CoffeeVariety(coffee_variety_id={self.coffee_variety_id}, "
                f"name={self.name}, description={self.description}, "
                f"rust_resistant={self.rust_resistant}, growth_habit={self.growth_habit}, "
                f"plant_density_sun={self.plant_density_sun}, "
                f"plant_density_shade={self.plant_density_shade}, "
                f"production={self.production}, altitude_min={self.altitude_min}, "
                f"altitude_max={self.altitude_max}, "
                f"plant_density_unit_id={self.plant_density_unit_id}, "
                f"production_unit_id={self.production_unit_id}, "
                f"altitude_unit_id={self.altitude_unit_id})>")
        
class Flowering(Base):
    __tablename__ = 'flowering'

    flowering_id = Column(Integer, primary_key=True, index=True, autoincrement=True, nullable=False)
    plot_id = Column(Integer, ForeignKey('plot.plot_id', ondelete="CASCADE", onupdate="CASCADE"), nullable=False)
    flowering_date = Column(Date, nullable=False)
    harvest_date = Column(Date, nullable=True, default=None)
    status_id = Column(Integer, ForeignKey('status.status_id', ondelete="RESTRICT", onupdate="CASCADE"), nullable=False)

    # Relaciones
    plot = relationship("Plot", back_populates="flowerings")
    status = relationship("Status", back_populates="flowerings")

    def __repr__(self):
        return f"<Flowering(flowering_id={self.flowering_id}, plot_id={self.plot_id}, flowering_date={self.flowering_date}, harvest_date={self.harvest_date}, status_id={self.status_id})>"