import json
import re

from fastapi import HTTPException
from pydantic import BaseModel, validator
from typing import List, Optional


class UserBase(BaseModel):
    name: str
    age: int
    gender: str
    email: str
    city: str
    interests: List[str]

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int

    class Config:
        orm_mode = True


class UserOptionalBase(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    interests: Optional[List[str]] = None


class UserUpdate(UserOptionalBase):
    pass




# class TUserBase(BaseModel):
#     name: str
#     age: int
#     gender: str
#     email: str
#     city: str
#     interests: List[str]
#     score: str