from sqlmodel import SQLModel, Relationship, Field


class Stalls(SQLModel, table=True):

    __tablename__ = "stalls"

    f_stall_id: int = Field(primary_key=True, default=None)
    f_stall_name: str
    f_stall_description: str

    stall_menu: list["StallMenu"] = Relationship(back_populates="stall")
    stall_owner: list["StallOwner"] = Relationship(back_populates="stall")
