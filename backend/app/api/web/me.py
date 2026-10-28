from fastapi import APIRouter

from app.core.auth import CurrentUser
from app.models import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/api", tags=["web"])


@router.get("/me", response_model=UserOut)
async def read_me(user: CurrentUser) -> User:
    return user
