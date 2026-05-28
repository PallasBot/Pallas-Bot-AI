from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from pyncm_async import (
    CreateNewSession,
    DumpSessionAsString,
    GetCurrentSession,
    LoadSessionFromString,
    Session,
    SetCurrentSession,
)
from pyncm_async.apis.login import (
    GetCurrentLoginStatus,
    LoginLogout,
    LoginViaCellphone,
    SetSendRegisterVerifcationCodeViaCellphone,
)

from app.core.logger import logger

SESSION_FILE = "data/ncm/session.txt"


class NCMLoginManager:
    _instance: Optional["NCMLoginManager"] = None
    session: Session | None
    initialized: bool

    def __new__(cls, *args: Any, **kwargs: Any) -> "NCMLoginManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "initialized"):
            self.session = None
            self.initialized = True
            self.load_saved_session()

    def load_saved_session(self) -> None:
        try:
            session_path: Path = Path(SESSION_FILE)
            if session_path.exists():
                if session_path.stat().st_size == 0:
                    logger.warning("session文件为空")
                    return

                with session_path.open("r", encoding="utf-8") as f:
                    session_str: str = f.read().strip()
                    if not session_str:
                        logger.warning("session文件为空")
                        return

                self.session = LoadSessionFromString(session_str)
                logger.info("成功使用缓存的session登录")
            else:
                logger.info("未找到session文件，将创建新的session")
                logger.info("私聊发送'网易云登录'来登录VIP账号")
        except FileNotFoundError:
            logger.info("未找到session文件，将创建新的session")
            logger.info("私聊发送'网易云登录'来登录VIP账号")
        except Exception as e:
            logger.error(f"使用缓存的session登录失败: {e}")

    async def _print_user_info(self) -> None:
        try:
            async with ncm_request_session():
                user_info = await GetCurrentLoginStatus()
            if isinstance(user_info, dict):
                profile: dict[str, Any] = user_info.get("profile", {})
                if isinstance(profile, dict):
                    nickname: str = profile.get("nickname", "Unknown")
                    user_id: int | str = profile.get("userId", "Unknown")
                    logger.info(f"当前登录用户: {nickname} (ID: {user_id})")
            else:
                logger.warning("无法获取有效的用户信息")
        except Exception as e:
            logger.warning(f"获取用户信息失败: {e}")

    def persist_session(self) -> None:
        if not self.session:
            return
        session_str: str = DumpSessionAsString(self.session)
        session_path: Path = Path(SESSION_FILE)
        session_path.parent.mkdir(exist_ok=True, parents=True)
        with session_path.open("w", encoding="utf-8") as f:
            f.write(session_str)
        logger.info("[+] 当前session已保存")

    def save_current_session(self) -> None:
        if not self.session:
            return
        try:
            self.persist_session()
            logger.info("登录成功")
            logger.info("可使用'网易云登出'退出账号")
        except Exception as e:
            logger.error(f"保存session失败: {e}")

    def get_session(self) -> str | None:
        if self.session:
            try:
                return DumpSessionAsString(self.session)
            except Exception as e:
                logger.error(f"获取session失败: {e}")
                return None
        return None

    def set_session(self, session_str: str | Session) -> None:
        try:
            if isinstance(session_str, Session):
                session = session_str
            else:
                session = LoadSessionFromString(session_str)
            self.session = session
            self.save_current_session()
        except Exception as e:
            logger.error(f"设置session失败: {e}")

    async def login_with_sms(self, phone: str, ctcode: int = 86) -> dict[str, Any]:
        try:
            async with ncm_request_session():
                result_data = await SetSendRegisterVerifcationCodeViaCellphone(phone, ctcode)
            if isinstance(result_data, dict):
                return result_data
            logger.warning("短信验证码返回异常")
            return {"code": 500, "message": "返回数据格式异常"}
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            return {"code": 500, "message": str(e)}

    async def verify_sms(self, phone: str, captcha: str, ctcode: int = 86) -> dict[str, Any]:
        try:
            async with ncm_request_session():
                await LoginViaCellphone(phone=phone, captcha=captcha, ctcode=ctcode)
                dumped = DumpSessionAsString(GetCurrentSession())
            self.session = LoadSessionFromString(dumped)
            self.persist_session()
            await self._print_user_info()
            logger.info("登录成功")
            logger.info("可使用'网易云登出'退出账号")
            return {"code": 200, "message": "登录成功"}
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return {"code": 500, "message": str(e)}

    async def logout(self) -> dict[str, Any]:
        try:
            async with ncm_request_session():
                result: dict[str, Any] = await LoginLogout()
            if result.get("code") == 200:
                logger.info("账号已退出")
            else:
                logger.warning(f"登出失败: {result.get('message')}")

            self.session = None

            session_path: Path = Path(SESSION_FILE)
            if session_path.exists():
                session_path.unlink()
                logger.info("已删除本地session文件")

            return {"code": 200, "message": "登出成功"}
        except Exception as e:
            logger.error(f"登出失败: {e}")
            return {"code": 500, "message": str(e)}


ncm_login_manager = NCMLoginManager()


@asynccontextmanager
async def ncm_request_session() -> AsyncIterator[Session]:
    """为当前 event loop 创建独立 httpx 会话（Celery 每任务新建/关闭 loop 时必需）。"""
    stored = ncm_login_manager.session
    if stored is not None:
        session = LoadSessionFromString(DumpSessionAsString(stored))
    else:
        session = CreateNewSession()
    async with session:
        yield session
