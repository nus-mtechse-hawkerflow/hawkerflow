from sqlmodel import SQLModel, Field, Relationship


class StallOwner(SQLModel, table=True):
    f_stall_owner_id: int = Field(default=None, primary_key=True)
    f_stall_id: int = Field(foreign_key="stalls.f_stall_id")
    f_stall_owner_name: str
    f_stall_owner_phone: str

    stall: list["Stalls"] = Relationship(back_populates="stall_owner")
