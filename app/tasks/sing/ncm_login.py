import json
from pathlib import Path

from pyncm import DumpSessionAsString, GetCurrentSession, LoadSessionFromString, SetCurrentSession
from pyncm.apis.login import (
    LoginViaCellphone,
    SetSendRegisterVerifcationCodeViaCellphone,
)

from app.core.logger import logger

SESSION_FILE = "data/ncm/session.json"


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
                    content = f.read().strip()
                    if not content:
                        logger.warning("session文件内容为空")
                        return

                    data = json.loads(content)
                    session_str = data["session"]

                self.session = LoadSessionFromString(session_str)
                SetCurrentSession(self.session)
                logger.info("成功使用缓存的session登录")
        except FileNotFoundError:
            logger.info("未找到session文件，将创建新的session")
        except json.JSONDecodeError as e:
            logger.error(f"session文件JSON格式错误: {e}")
            try:
                session_path = Path(SESSION_FILE)
                if session_path.exists():
                    session_path.unlink()
                    logger.info("已删除损坏的session文件")
            except Exception as remove_error:
                logger.error(f"删除损坏的session文件失败: {remove_error}")
        except Exception as e:
            logger.error(f"使用缓存的session登录失败: {e}")

    def save_current_session(self):
        if self.session:
            try:
                session_str = DumpSessionAsString(self.session)
                session_path = Path(SESSION_FILE)
                session_path.parent.mkdir(exist_ok=True, parents=True)
                with session_path.open("w", encoding="utf-8") as f:
                    json.dump({"session": session_str}, f, ensure_ascii=False, indent=2)
                logger.info("[+] 当前session已保存")
            except Exception as e:
                logger.error(f"保存session失败: {e}")

    def get_session(self):
        if self.session:
            try:
                return DumpSessionAsString(self.session)
            except Exception as e:
                logger.error(f"获取session失败: {e}")
                return None
        return None

    def set_session(self, session):
        self.session = session
        SetCurrentSession(session)
        self.save_current_session()

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
                self.session = GetCurrentSession()
                self.save_current_session()
            return result
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return {"code": 500, "message": str(e)}


ncm_login_manager = NCMLoginManager()
