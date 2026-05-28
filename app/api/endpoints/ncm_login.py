from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.ncm_login import (
    CellphoneSMSLoginRequest,
    LoginResponse,
    LogoutResponse,
    SendSMSRequest,
)
from app.tasks.sing.ncm_login import ncm_login_manager

router = APIRouter(prefix="/ncm", tags=["网易云音乐登录"])


@router.get("/login/status")
async def get_login_status() -> LoginResponse:
    session = ncm_login_manager.get_session()
    return LoginResponse(success=bool(session), message="已登录" if session else "未登录", session=session)


@router.post("/login/cellphone/send-sms")
async def send_sms(request: SendSMSRequest):
    result = await ncm_login_manager.login_with_sms(phone=request.phone, ctcode=request.ctcode)
    return JSONResponse({"code": result.get("code"), "message": result.get("message")})


@router.post("/login/cellphone/verify-sms", response_model=LoginResponse)
async def verify_sms(request: CellphoneSMSLoginRequest):
    result = await ncm_login_manager.verify_sms(
        phone=request.phone, captcha=request.captcha, ctcode=request.ctcode
    )
    if result.get("code") == 200:
        return LoginResponse(
            success=True,
            message="登录成功",
            session=ncm_login_manager.get_session(),
        )
    return LoginResponse(success=False, message=result.get("message", "登录失败"))


@router.post("/login/logout", response_model=LogoutResponse)
async def logout():
    result = await ncm_login_manager.logout()
    if result.get("code") == 200:
        return LogoutResponse(success=True, message="已登出")
    return LogoutResponse(success=False, message=result.get("message", "登出失败"))
