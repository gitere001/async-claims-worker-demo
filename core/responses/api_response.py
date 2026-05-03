from typing import Generic, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    message: str
    data: Optional[T] = None

    @classmethod
    def ok(cls, data: T, message: str = "Success") -> "ApiResponse[T]":
        return cls(success=True, message=message, data=data)

    @classmethod
    def error(cls, message: str) -> "ApiResponse[None]":
        return cls(success=False, message=message, data=None)
