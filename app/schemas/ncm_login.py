from pydantic import BaseModel


class CellphoneSMSLoginRequest(BaseModel):
    phone: str
    captcha: str
    ctcode: int = 86


class SendSMSRequest(BaseModel):
    phone: str
    ctcode: int = 86


class LoginResponse(BaseModel):
    success: bool
    message: str
    session: str | None = None


class LogoutResponse(BaseModel):
    success: bool
    message: str
