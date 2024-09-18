

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

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

# Modelo para UserRoleFarm (relación entre usuarios, roles y fincas)
class UserRoleFarm(Base):
    __tablename__ = 'user_role_farm'

    user_role_farm_id = Column(Integer, primary_key=True)
    role_id = Column(Integer, ForeignKey('role.role_id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.user_id'), nullable=False)
    farm_id = Column(Integer, ForeignKey('farm.farm_id'), nullable=False)

    # Relaciones
    role = relationship("Role")
    user = relationship("User")
    farm = relationship("Farm")


# Modelo para Role
class Role(Base):
    __tablename__ = 'role'

    role_id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    
     # Relación con RolePermission (permisos asociados a este rol)
    permissions = relationship("RolePermission", back_populates="role")

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
    status_id = Column(Integer, ForeignKey("status.status_id"), nullable=False)

    # Relación con Status (usando una cadena para resolver el nombre de la clase)
    status = relationship("Status", back_populates="users")

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