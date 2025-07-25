from pathlib import Path

from pyncm import DumpSessionAsString, GetCurrentSession, LoadSessionFromString, SetCurrentSession
from pyncm.apis.login import (
    GetCurrentLoginStatus,
    LoginLogout,
    LoginViaCellphone,
    SetSendRegisterVerifcationCodeViaCellphone,
)

from app.core.logger import logger

SESSION_FILE = "data/ncm/session.txt"


class NCMLoginManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.session = None
            self.initialized = True
            self.load_saved_session()

    def load_saved_session(self):
        try:
            session_path = Path(SESSION_FILE)
            if session_path.exists():
                if session_path.stat().st_size == 0:
                    logger.warning("session文件为空")
                    return

                with session_path.open("r", encoding="utf-8") as f:
                    session_str = f.read().strip()
                    if not session_str:
                        logger.warning("session文件内容为空")
                        return

                self.session = LoadSessionFromString(session_str)
                SetCurrentSession(self.session)
                logger.info("成功使用缓存的session登录")

                # 输出用户信息
                try:
                    user_info = GetCurrentLoginStatus()
                    if user_info.get("code") == 200 and user_info.get("profile"):
                        profile = user_info["profile"]
                        nickname = profile.get("nickname", "Unknown")
                        user_id = profile.get("userId", "Unknown")
                        logger.info(f"当前登录用户: {nickname} (ID: {user_id})")
                    else:
                        logger.warning("无法获取用户信息")
                except Exception as e:
                    logger.warning(f"获取用户信息失败: {e}")
            else:
                logger.info("未找到session文件，将创建新的session")
        except FileNotFoundError:
            logger.info("未找到session文件，将创建新的session")
        except Exception as e:
            logger.error(f"使用缓存的session登录失败: {e}")

    def save_current_session(self):
        if self.session:
            try:
                session_str = DumpSessionAsString(self.session)
                session_path = Path(SESSION_FILE)
                session_path.parent.mkdir(exist_ok=True, parents=True)
                with session_path.open("w", encoding="utf-8") as f:
                    f.write(session_str)
                logger.info("[+] 当前session已保存")
            except Exception as e:
                logger.error(f"保存session失败: {e}")

    def get_session(self):
        """获取当前session字符串"""
        if self.session:
            try:
                session_str = DumpSessionAsString(self.session)
                return session_str
            except Exception as e:
                logger.error(f"获取session失败: {e}")
                return None
        return None

    def set_session(self, session_str: str):
        """设置session"""
        try:
            session = LoadSessionFromString(session_str)
            self.session = session
            SetCurrentSession(session)
            self.save_current_session()
        except Exception as e:
            logger.error(f"设置session失败: {e}")

    def login_with_sms(self, phone: str, ctcode: int = 86) -> dict:
        try:
            result = SetSendRegisterVerifcationCodeViaCellphone(phone, ctcode)
            return result
        except Exception as e:
            logger.error(f"发送验证码失败: {e}")
            return {"code": 500, "message": str(e)}

    def verify_sms(self, phone: str, captcha: str, ctcode: int = 86) -> dict:
        try:
            result = LoginViaCellphone(phone=phone, captcha=captcha, ctcode=ctcode)
            if result.get("code") == 200:
                logger.info("短信验证登录成功")
                self.session = GetCurrentSession()
                self.save_current_session()

                try:
                    user_info = GetCurrentLoginStatus()
                    if user_info.get("code") == 200 and user_info.get("profile"):
                        profile = user_info["profile"]
                        nickname = profile.get("nickname", "Unknown")
                        user_id = profile.get("userId", "Unknown")
                        logger.info(f"当前登录用户: {nickname} (ID: {user_id})")
                    else:
                        logger.warning("无法获取用户信息")
                except Exception as e:
                    logger.warning(f"获取用户信息失败: {e}")
            else:
                logger.warning(f"登录验证失败，错误码: {result.get('code')}, 信息: {result.get('message')}")
            return result
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return {"code": 500, "message": str(e)}

    def logout(self) -> dict:
        """登出账号"""
        try:
            result = LoginLogout()
            if result.get("code") == 200:
                logger.info("登出成功")
            else:
                logger.warning(f"登出失败，错误信息: {result.get('message')}")

            # 清除本地session
            self.session = None

            # 删除session文件
            session_path = Path(SESSION_FILE)
            if session_path.exists():
                session_path.unlink()
                logger.info("已删除本地session文件")

            logger.info("账号已登出")
            return {"code": 200, "message": "登出成功"}
        except Exception as e:
            logger.error(f"登出失败: {e}")
            return {"code": 500, "message": str(e)}


ncm_login_manager = NCMLoginManager()
