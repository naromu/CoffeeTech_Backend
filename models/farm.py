from sqlalchemy import Column, Integer, String, Numeric
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Farm(Base):
    __tablename__ = "farm"

    farm_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    area_farm = Column(Numeric(10, 2), nullable=False)
