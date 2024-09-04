from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from models.user import User
from models.farm import Farm
from models.user_role_farm import UserRoleFarm
from models.role import Role
from utils.security import get_current_user
from dataBase import get_db_session

router = APIRouter()

# Esquema para la creación y actualización de una finca
class FarmBase(BaseModel):
    name: str
    area_farm: float

class FarmCreate(FarmBase):
    pass

class FarmUpdate(FarmBase):
    pass

# Crear una finca
@router.post("/create-farms", response_model=dict)
def create_farm(farm: FarmCreate, db: Session = Depends(get_db_session), current_user: User = Depends(get_current_user)):
    # Verificar si el rol 'Dueño de la finca' existe, si no, crearlo
    owner_role = db.query(Role).filter(Role.name == "Dueño de la finca").first()
    if not owner_role:
        owner_role = Role(name="Dueño de la finca")
        db.add(owner_role)
        db.commit()
        db.refresh(owner_role)
    
    # Crear la finca
    new_farm = Farm(name=farm.name, area_farm=farm.area_farm)
    db.add(new_farm)
    db.commit()
    db.refresh(new_farm)

    # Asignar al usuario como dueño
    user_role_farm = UserRoleFarm(user_id=current_user.user_id, farm_id=new_farm.farm_id, role_id=owner_role.role_id)
    db.add(user_role_farm)
    db.commit()

    return {"message": "Finca creada exitosamente", "farm_id": new_farm.farm_id}

# Obtener una finca por ID
@router.get("/list-farms/ {farm_id}", response_model=dict)
def get_farm(farm_id: int, db: Session = Depends(get_db_session), current_user: User = Depends(get_current_user)):
    farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Finca no encontrada")
    
    return {"farm_id": farm.farm_id, "name": farm.name, "area_farm": farm.area_farm}

# Actualizar una finca
@router.put("/update-farms/{farm_id}", response_model=dict)
def update_farm(farm_id: int, farm_update: FarmUpdate, db: Session = Depends(get_db_session), current_user: User = Depends(get_current_user)):
    farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Finca no encontrada")

    farm.name = farm_update.name
    farm.area_farm = farm_update.area_farm
    db.commit()

    return {"message": "Finca actualizada exitosamente", "farm_id": farm.farm_id}

# Eliminar una finca
@router.delete("/delete-farms/{farm_id}", response_model=dict)
def delete_farm(farm_id: int, db: Session = Depends(get_db_session), current_user: User = Depends(get_current_user)):
    farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Finca no encontrada")
    
    db.delete(farm)
    db.commit()

    return {"message": "Finca eliminada exitosamente"}

