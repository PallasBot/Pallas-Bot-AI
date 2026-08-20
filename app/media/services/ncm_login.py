from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from pyncm_async import (
    CreateNewSession,
    DumpSessionAsString,
    GetCurrentSession,
    LoadSessionFromString,
    Session,
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
                    logger.warning("ncm session file is empty")
                    return

                with session_path.open("r", encoding="utf-8") as f:
                    session_str: str = f.read().strip()
                    if not session_str:
                        logger.warning("ncm session file is empty")
                        return

                self.session = LoadSessionFromString(session_str)
                logger.info("ncm session loaded from saved cache")
            else:
                logger.info("ncm session file not found, will create a new session")
                logger.info("send '网易云登录' in private chat to log into the VIP account")
        except FileNotFoundError:
            logger.info("ncm session file not found, will create a new session")
            logger.info("send '网易云登录' in private chat to log into the VIP account")
        except Exception as e:
            logger.error("failed to login with cached ncm session: {}", e)

    async def _print_user_info(self) -> None:
        try:
            async with ncm_request_session():
                user_info = await GetCurrentLoginStatus()
            if isinstance(user_info, dict):
                profile: dict[str, Any] = user_info.get("profile", {})
                if isinstance(profile, dict):
                    nickname: str = profile.get("nickname", "Unknown")
                    user_id: int | str = profile.get("userId", "Unknown")
                    logger.info("current ncm user: {} (ID: {})", nickname, user_id)
            else:
                logger.warning("failed to get valid ncm user info")
        except Exception as e:
            logger.warning("failed to fetch ncm user info: {}", e)

    def persist_session(self) -> None:
        if not self.session:
            return
        session_str: str = DumpSessionAsString(self.session)
        session_path: Path = Path(SESSION_FILE)
        session_path.parent.mkdir(exist_ok=True, parents=True)
        with session_path.open("w", encoding="utf-8") as f:
            f.write(session_str)
        logger.info("ncm session persisted")

    def save_current_session(self) -> None:
        if not self.session:
            return
        try:
            self.persist_session()
            logger.info("ncm login succeeded")
            logger.info("send '网易云登出' in private chat to log out")
        except Exception as e:
            logger.error("failed to save ncm session: {}", e)

    def get_session(self) -> str | None:
        if self.session:
            try:
                return DumpSessionAsString(self.session)
            except Exception as e:
                logger.error("failed to dump ncm session: {}", e)
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
            logger.error("failed to set ncm session: {}", e)

    async def login_with_sms(self, phone: str, ctcode: int = 86) -> dict[str, Any]:
        try:
            async with ncm_request_session():
                result_data = await SetSendRegisterVerifcationCodeViaCellphone(phone, ctcode)
            if isinstance(result_data, dict):
                return result_data
            logger.warning("unexpected sms code response")
            return {"code": 500, "message": "返回数据格式异常"}
        except Exception as e:
            logger.error("failed to send sms code: {}", e)
            return {"code": 500, "message": str(e)}

    async def verify_sms(self, phone: str, captcha: str, ctcode: int = 86) -> dict[str, Any]:
        try:
            async with ncm_request_session():
                await LoginViaCellphone(phone=phone, captcha=captcha, ctcode=ctcode)
                dumped = DumpSessionAsString(GetCurrentSession())
            self.session = LoadSessionFromString(dumped)
            self.persist_session()
            await self._print_user_info()
            logger.info("ncm login succeeded")
            logger.info("send '网易云登出' in private chat to log out")
            return {"code": 200, "message": "登录成功"}
        except Exception as e:
            logger.error("ncm login failed: {}", e)
            return {"code": 500, "message": str(e)}

    async def logout(self) -> dict[str, Any]:
        try:
            async with ncm_request_session():
                result: dict[str, Any] = await LoginLogout()
            if result.get("code") == 200:
                logger.info("ncm account logged out")
            else:
                logger.warning("ncm logout failed: {}", result.get("message"))

            self.session = None

            session_path: Path = Path(SESSION_FILE)
            if session_path.exists():
                session_path.unlink()
                logger.info("local ncm session file removed")

            return {"code": 200, "message": "登出成功"}
        except Exception as e:
            logger.error("ncm logout failed: {}", e)
            return {"code": 500, "message": str(e)}


ncm_login_manager = NCMLoginManager()


@asynccontextmanager
async def ncm_request_session() -> AsyncIterator[Session]:
    """为当前 event loop 创建独立 httpx 会话（每任务新建 loop 时必需）。"""
    stored = ncm_login_manager.session
    if stored is not None:
        session = LoadSessionFromString(DumpSessionAsString(stored))
    else:
        session = CreateNewSession()
    async with session:
        yield session
