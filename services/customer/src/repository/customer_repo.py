from sqlmodel import Session, select
from sqlalchemy import Engine

from entities.customer_loyalty import CustomerLoyalty
from entities.customer import Customer
from models.customer_details import CustomerDetails


class CustomerRepo:
    def __init__(self, engine: Engine):
        self._engine = engine

    def get_customer_by_email(self, email: str):
        with Session(self._engine) as session:
            statement = select(Customer).where(Customer.f_email == email)
            return session.exec(statement).first()

    def create_customer(self, customer_details: CustomerDetails):
        customer = Customer(
            f_email=customer_details.email,
            f_first_name=customer_details.first_name,
            f_last_name=customer_details.last_name,
            f_phone_number=customer_details.phone_number
        )

        customer_loyalty = CustomerLoyalty(
            f_loyalty_tier="BRONZE",
            f_loyalty_points=0
        )

        customer.customer_loyalty.append(customer_loyalty)

        with Session(self._engine) as session:
            session.add(customer)
            session.commit()
            session.refresh(customer)

            return customer

    def update_customer(self, customer_details: CustomerDetails):
        with Session(self._engine) as session:
            customer = session.get(Customer, customer_details.email)
            customer.f_first_name = customer_details.first_name
            customer.f_last_name = customer_details.last_name
            customer.f_phone_number = customer_details.phone_number
            session.commit()
            session.refresh(customer)
            return customer
