from pathlib import Path
from typing import Any, Optional

from pyncm import DumpSessionAsString, GetCurrentSession, LoadSessionFromString, Session, SetCurrentSession
from pyncm.apis.login import (
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
                SetCurrentSession(self.session)
                logger.info("成功使用缓存的session登录")

                # 输出用户信息
                self._print_user_info()
            else:
                logger.info("未找到session文件，将创建新的session")
                logger.info("私聊发送'网易云登录'来登录VIP账号")
        except FileNotFoundError:
            logger.info("未找到session文件，将创建新的session")
            logger.info("私聊发送'网易云登录'来登录VIP账号")
        except Exception as e:
            logger.error(f"使用缓存的session登录失败: {e}")

    def _print_user_info(self) -> None:
        """输出用户信息的通用方法"""
        try:
            user_info = GetCurrentLoginStatus()
            if isinstance(user_info, dict):
                profile: dict[str, Any] = user_info.get("profile", {})
                if isinstance(profile, dict):
                    nickname: str = profile.get("nickname", "Unknown")
                    user_id: int | str = profile.get("userId", "Unknown")
                    logger.info(f"当前登录用户: {nickname} (ID: {user_id})")
                else:
                    pass
            else:
                logger.warning("无法获取有效的用户信息")
        except Exception as e:
            logger.warning(f"获取用户信息失败: {e}")

    def save_current_session(self) -> None:
        if self.session:
            try:
                session_str: str = DumpSessionAsString(self.session)
                session_path: Path = Path(SESSION_FILE)
                session_path.parent.mkdir(exist_ok=True, parents=True)
                with session_path.open("w", encoding="utf-8") as f:
                    f.write(session_str)
                logger.info("登录成功")
                # 输出用户信息
                self._print_user_info()
                logger.info("可使用'网易云登出'退出账号")
                logger.info("[+] 当前session已保存")
            except Exception as e:
                logger.error(f"保存session失败: {e}")

    def get_session(self) -> str | None:
        """获取当前session字符串"""
        if self.session:
            try:
                session_str: str = DumpSessionAsString(self.session)
                return session_str
            except Exception as e:
                logger.error(f"获取session失败: {e}")
                return None
        return None

    def set_session(self, session_str: str | Session) -> None:
        """设置session"""
        try:
            if isinstance(session_str, Session):
                session = session_str
            else:
                session = LoadSessionFromString(session_str)
            self.session = session
            SetCurrentSession(session)
            self.save_current_session()
        except Exception as e:
            logger.error(f"设置session失败: {e}")

    def login_with_sms(self, phone: str, ctcode: int = 86) -> dict[str, Any]:
        try:
            result_data = SetSendRegisterVerifcationCodeViaCellphone(phone, ctcode)
            if isinstance(result_data, dict):
                return result_data
            else:
                logger.warning("短信验证码返回异常")
                return {"code": 500, "message": "返回数据格式异常"}
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            return {"code": 500, "message": str(e)}

    def verify_sms(self, phone: str, captcha: str, ctcode: int = 86) -> dict[str, Any]:
        try:
            result: dict[str, Any] = LoginViaCellphone(phone=phone, captcha=captcha, ctcode=ctcode)
            if result.get("code") == 200:
                self.session = GetCurrentSession()
                self.save_current_session()

            else:
                logger.warning(f"登录验证失败{result.get('message')}")
            return result
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return {"code": 500, "message": str(e)}

    def logout(self) -> dict[str, Any]:
        """登出账号"""
        try:
            result: dict[str, Any] = LoginLogout()
            if result.get("code") == 200:
                logger.info("账号已退出")
            else:
                logger.warning(f"登出失败: {result.get('message')}")

            # 清除本地session
            self.session = None

            # 删除session文件
            session_path: Path = Path(SESSION_FILE)
            if session_path.exists():
                session_path.unlink()
                logger.info("已删除本地session文件")

            return {"code": 200, "message": "登出成功"}
        except Exception as e:
            logger.error(f"登出失败: {e}")
            return {"code": 500, "message": str(e)}


ncm_login_manager = NCMLoginManager()
