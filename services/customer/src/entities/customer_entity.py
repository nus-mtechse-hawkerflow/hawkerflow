from pydantic import EmailStr
from sqlmodel import SQLModel, Field, Relationship


class Customer(SQLModel, table=True):
    __tablename__ = "customer"

    f_id: int = Field(default=None, primary_key=True)
    f_first_name: str
    f_last_name: str
    f_user_id: str
    f_username: str
    f_email: EmailStr

    customer_loyalty_points: list["CustomerLoyaltyPoints"] = Relationship(back_populates="customer")
