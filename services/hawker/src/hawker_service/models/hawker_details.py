from pydantic import BaseModel


class StallMenu(BaseModel):
    name: str
    price: float
    description: str


class StallOwner(BaseModel):
    name: str
    phone: str


class HawkerDetails(BaseModel):
    stall_name: str
    stall_number: str
    stall_description: str
    stall_location: str
    stall_menu: list[StallMenu]
    stall_owner: StallOwner
