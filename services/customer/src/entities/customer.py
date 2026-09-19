from datetime import datetime, timezone

from pydantic import EmailStr
from sqlmodel import SQLModel, Field, Relationship


class Customer(SQLModel, table=True):
    __tablename__ = "customer"

    f_id: int = Field(default=None, primary_key=True)
    f_first_name: str
    f_last_name: str
    f_email: EmailStr = Field(unique=True)
    f_phone_number: int = Field(unique=True)
    f_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    customer_loyalty: list["CustomerLoyalty"] = Relationship(back_populates="customer")
