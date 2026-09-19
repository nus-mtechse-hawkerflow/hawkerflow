from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from models.customer_details import CustomerDetails
from user_service.user_service import UserService

cust_router = APIRouter(prefix="/v1/customer")


def get_user_service(request: Request):
    return request.app.state.user_service


@cust_router.post("/register")
async def register_user(
        customer_details: CustomerDetails,
        user_service: Annotated[UserService, None] = Depends(get_user_service)
):

    customer = user_service.register_customer(customer_details)
    return JSONResponse(
        content={
            "cust_id": customer.f_id,
            "cust_name": customer.f_first_name + " " + customer.f_last_name,
            "created_at": customer.f_created_at.isoformat()
        }
    )
