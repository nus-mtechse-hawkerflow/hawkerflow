from datetime import datetime, timezone

from sqlmodel import SQLModel, Field, Relationship


class StallMenu(SQLModel, table=True):

    __tablename__ = "stall_menu"

    f_stall_id: int = Field(foreign_key="stalls.f_stall_id")
    f_menu_id: int = Field(default=None, primary_key=True)
    f_menu_name: str
    f_menu_price: float
    f_menu_description: str
    f_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    f_updated_at: datetime = Field(default=None, nullable=True)

    stall: "Stalls" = Relationship(back_populates="stall_menu")
