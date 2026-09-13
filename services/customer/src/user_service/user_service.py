from models.customer_details import CustomerDetails
from repository.customer_repo import CustomerRepo
from entities.customer import Customer


class UserService:
    def __init__(self, user_repo: CustomerRepo):
        self._repository = user_repo


    def register_customer(self, customer_details: CustomerDetails) -> Customer:
        return self._repository.create_customer(customer_details)
