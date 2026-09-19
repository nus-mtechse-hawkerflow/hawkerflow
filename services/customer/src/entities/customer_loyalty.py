from datetime import datetime, timezone

from sqlmodel import SQLModel, Field, Column, DateTime, text, Relationship


class CustomerLoyalty(SQLModel, table=True):
    __tablename__ = "customer_loyalty"

    f_customer_id: str = Field(
        default=None,
        index=True,
        nullable=False,
        primary_key=True,
        foreign_key="customer.f_id"
    )
    f_loyalty_tier: str = Field(default="BRONZE")
    f_loyalty_points: int
    f_created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False
        )
    )
    f_last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("CURRENT_TIMESTAMP"),
            nullable=False
        )
    )
    f_last_order_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )

    customer: "Customer" = Relationship(back_populates="customer_loyalty")
