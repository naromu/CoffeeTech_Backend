from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, Boolean, Date, Sequence, Double
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

# Modelo para Farm (Finca)
class Farm(Base):
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
    __tablename__ = 'role'

    role_id = Column(Integer, primary_key=True, server_default=Sequence('role_role_id_seq').next_value())
    name = Column(String(50), nullable=False, unique=True)

    # Relación con RolePermission
    permissions = relationship("RolePermission", back_populates="role")
    user_roles_farms = relationship('UserRoleFarm', back_populates='role')


# Modelo para UnitOfMeasureType
class UnitOfMeasureType(Base):
    __tablename__ = 'unit_of_measure_type'

    unit_of_measure_type_id = Column(Integer, primary_key=True, server_default=Sequence('unit_of_measure_type_unit_of_measure_type_id_seq').next_value())
    name = Column(String(50), nullable=False)

    # Relación con UnitOfMeasure
    units_of_measure = relationship("UnitOfMeasure", back_populates="unit_of_measure_type")


# Modelo para UnitOfMeasure
class UnitOfMeasure(Base):
    __tablename__ = 'unit_of_measure'

    unit_of_measure_id = Column(Integer, primary_key=True, server_default=Sequence('unit_of_measure_unit_of_measure_id_seq').next_value())
    name = Column(String(50), nullable=False)
    abbreviation = Column(String(10), nullable=False)
    unit_of_measure_type_id = Column(Integer, ForeignKey('unit_of_measure_type.unit_of_measure_type_id'), nullable=False)

    # Relación con UnitOfMeasureType
    unit_of_measure_type = relationship("UnitOfMeasureType", back_populates="units_of_measure")


# Definición del modelo StatusType
class StatusType(Base):
    __tablename__ = 'status_type'

    status_type_id = Column(Integer, primary_key=True, server_default=Sequence('status_type_status_type_id_seq').next_value())
    name = Column(String(50), nullable=False)

    # Relación con Status
    statuses = relationship("Status", back_populates="status_type")


# Definición del modelo Status
class Status(Base):
    __tablename__ = "status"

    status_id = Column(Integer, primary_key=True, server_default=Sequence('status_status_id_seq').next_value())
    name = Column(String(45), nullable=False)
    description = Column(String(255), nullable=True)
    status_type_id = Column(Integer, ForeignKey("status_type.status_type_id"), nullable=False)

    # Relación con StatusType
    status_type = relationship("StatusType", back_populates="statuses")

    # Relación con User
    users = relationship("User", back_populates="status")
    
    # Relación con Notification
    notifications = relationship("Notification", back_populates="status")



# Definición del modelo User
class User(Base):
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
    __tablename__ = 'permission'

    permission_id = Column(Integer, primary_key=True, index=True, server_default=Sequence('permission_permission_id_seq').next_value())
    description = Column(String(200), nullable=False)
    name = Column(String(50), nullable=True, unique=True)

    # Relación con RolePermission
    roles = relationship("RolePermission", back_populates="permission")


# Modelo para RolePermission
class RolePermission(Base):
    __tablename__ = 'role_permission'

    role_id = Column(Integer, ForeignKey('role.role_id'), primary_key=True, nullable=False)
    permission_id = Column(Integer, ForeignKey('permission.permission_id'), primary_key=True, nullable=False)

    # Relaciones con Role y Permission
    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")


# Modelo para Invitation
class Invitation(Base):
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
    __tablename__ = 'notification_type'

    notification_type_id = Column(Integer, primary_key=True, server_default=Sequence('notification_type_notification_type_id_seq').next_value())
    name = Column(String(50), nullable=False)

    # Relación con Notification
    notifications = relationship("Notification", back_populates="notification_type")


# Modelo para Notification
class Notification(Base):
    __tablename__ = 'notifications'

    notifications_id = Column(Integer, primary_key=True, server_default=Sequence('notifications_notifications_id_seq').next_value())
    message = Column(String(255), nullable=True)
    date = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    invitation_id = Column(Integer, ForeignKey('invitation.invitation_id'), nullable=True)
    notification_type_id = Column(Integer, ForeignKey('notification_type.notification_type_id'), nullable=True)
    reminder_time = Column(DateTime, nullable=True)
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


# Modelo para CoffeeVariety
class CoffeeVariety(Base):
    __tablename__ = 'coffee_variety'

    coffee_variety_id = Column(Integer, primary_key=True, index=True, server_default=Sequence('coffee_variety_coffee_variety_id_seq').next_value())
    name = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    rust_resistant = Column(Boolean, nullable=True)
    growth_habit = Column(String(50), nullable=True)
    plant_density_sun = Column(Numeric(10, 2), nullable=True)
    plant_density_shade = Column(Numeric(10, 2), nullable=True)
    production = Column(Numeric(10, 2), nullable=True)
    altitude_min = Column(Integer, nullable=True)
    altitude_max = Column(Integer, nullable=True)
    plant_density_unit_id = Column(Integer, ForeignKey('unit_of_measure.unit_of_measure_id'), nullable=True)
    production_unit_id = Column(Integer, ForeignKey('unit_of_measure.unit_of_measure_id'), nullable=True)
    altitude_unit_id = Column(Integer, ForeignKey('unit_of_measure.unit_of_measure_id'), nullable=True)

    # Relaciones
    plots = relationship("Plot", back_populates="coffee_variety")


# Modelo para FloweringType (Tipo de Floración)
class FloweringType(Base):
    __tablename__ = 'flowering_type'

    flowering_type_id = Column(Integer, primary_key=True, server_default=Sequence('flowering_type_flowering_type_id_seq').next_value())
    name = Column(String(50), nullable=False)

    # Relación con Flowering
    flowerings = relationship("Flowering", back_populates="flowering_type")


# Modelo para Flowering (Floración)
class Flowering(Base):
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