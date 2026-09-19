from pydantic import BaseModel, EmailStr


class CustomerDetails(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone_number: int
