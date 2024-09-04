from sqlalchemy import Column, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class UserRoleFarm(Base):
    __tablename__ = "user_role_farm"

    user_role_farm_id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    farm_id = Column(Integer, nullable=False)
