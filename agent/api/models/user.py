from pydantic import BaseModel

class LoginInput(BaseModel):
    user_id: str
    userpwd: str

class RegisterInput(BaseModel):
    username: str
    user_id: str
    userpwd: str
