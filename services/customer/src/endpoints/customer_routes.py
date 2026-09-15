from fastapi import APIRouter


cust_router = APIRouter(prefix="/v1/customer")


@cust_router.post("/register")
async def register_user():
    return {"message": "User registered"}
