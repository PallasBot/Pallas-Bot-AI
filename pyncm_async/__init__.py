# -*- coding: utf-8 -*-
# Modified locally on 2026-10-08.
"""PyNCM_Async 网易云音乐 Python 异步 API / 下载工具

PyNCM_Async 包装的网易云音乐 API 的使用非常简单::

    >>> from pyncm_async import apis
    # 登录
    >>> await apis.LoginViaCellphone(phone="[..]", password="[..]", ctcode=86, remeberLogin=True))
    # 获取歌曲信息
    >>> await apis.track.GetTrackAudio(29732235)
    {'data': [{'id': 29732235, 'url': 'http://m701.music...
    # 获取歌曲详情
    >>> await apis.track.GetTrackDetail(29732235)
    {'songs': [{'name': 'Supernova', 'id': 2...
    # 获取歌曲评论
    >>> await apis.track.GetTrackComments(29732235)
    {'isMusician': False, 'userId': -1, 'topComments': [], 'moreHot': True, 'hotComments': [{'user': {'locationInfo': None, 'liveIn ...

PyNCM_Async 的所有 API 请求都将经过单例的 `pyncm_asycn.Session` 发出，管理此单例可以使用::

    >>> session = pyncm_asycn.GetCurrentSession()
    >>> pyncm_asycn.SetCurrentSession(session)
    >>> pyncm_asycn.SetNewSession()

PyNCM_Async 同时提供了相应的 Session 序列化函数，用于其储存及管理::

    >>> save = pyncm_asycn.DumpSessionAsString()
    >>> pyncm_asycn.SetNewSession(
            pyncm_asycn.LoadSessionFromString(save)
        )

# 注意事项
    - (PR#11) 海外用户可能经历 460 "Cheating" 问题，可通过添加以下 Header 解决: `X-Real-IP = 118.88.88.88`
"""

__VERSION_MAJOR__ = 1
__VERSION_MINOR__ = 8
__VERSION_PATCH__ = 2

__version__ = f"{__VERSION_MAJOR__}.{__VERSION_MINOR__}.{__VERSION_PATCH__}"

import asyncio
from contextvars import ContextVar
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy, eff_request_host
from urllib.parse import urlsplit
from urllib.request import Request
from typing import Text, Union
from time import time

from .utils import GenerateSDeviceId, GenerateWNMCID
from .utils.crypto import EapiEncrypt, EapiDecrypt, HexCompose
import httpx, logging, json, os, re
import base64
import binascii
import math
import zlib

logger = logging.getLogger("pyncm_asycn.api")
if "PYNCM_ASYNC_DEBUG" in os.environ:
    debug_level = os.environ["PYNCM_ASYNC_DEBUG"].upper()
    if not debug_level in {"CRITICAL", "DEBUG", "ERROR", "FATAL", "INFO", "WARNING"}:
        debug_level = "DEBUG"
    logging.basicConfig(
        level=debug_level, format="[%(levelname).4s] %(name)s %(message)s"
    )

DEVICE_ID_DEFAULT = "pyncm!"
# This sometimes fails with some strings, for no particular reason. Though `pyncm!` seem to work everytime..?
# Though with this, all pyncm users would then be sharing the same device Id.
# Don't think that would be of any issue though...
"""默认 deviceID"""
SESSION_STACK = dict()
_session_context = ContextVar("pyncm_async_session_stack", default=())
_AUTH_COOKIE_NAMES = {"MUSIC_U", "MUSIC_A", "__csrf"}
_COOKIE_ORIGIN = "pyncm_host_only_origin"
# ponytail: fixed 1 MiB JSON ceiling; raise only if legitimate session payloads exceed it.
_SESSION_JSON_MAX = 1 << 20
_SESSION_STRING_MAX = 2 * (_SESSION_JSON_MAX + 128)


class _CookiePolicy(DefaultCookiePolicy):
    def return_ok_domain(self, cookie, request):
        if cookie.name in _AUTH_COOKIE_NAMES and not cookie.domain_specified:
            try:
                origin = _host_only_cookie_origin(cookie.domain, cookie._rest)
                host = httpx.URL(request.get_full_url()).raw_host.decode("ascii")
            except (ValueError, httpx.InvalidURL):
                return False
            if host != origin:
                return False
        return super().return_ok_domain(cookie, request)


def _canonical_cookie_domain(domain):
    if not domain:
        return ""
    plain = domain[1:] if domain.startswith(".") else domain
    if any(char in plain for char in "/\\@?#"):
        raise ValueError("Invalid cookie domain")
    if plain.startswith("["):
        end = plain.find("]")
        host = _cookie_host(plain[:end + 1])
        if plain == _cookie_storage_host(host):
            return host
    elif ":" in plain:
        raise ValueError("Invalid cookie domain")
    return _cookie_host(plain)


def _cookie_url(configured_host):
    if not isinstance(configured_host, str) or not configured_host or any(
        char.isspace() for char in configured_host
    ):
        raise ValueError("Invalid Session.HOST")
    parts = urlsplit(configured_host if "://" in configured_host else f"//{configured_host}")
    host = parts.hostname
    if (
        not host or host.startswith(".") or parts.username is not None
        or parts.password is not None or parts.path not in {"", "/"}
        or parts.query or parts.fragment or parts.scheme not in {"", "http", "https"}
    ):
        raise ValueError("Invalid Session.HOST")
    parts.port  # Validate a configured port before changing authentication state.
    try:
        url = httpx.URL(configured_host if parts.scheme else f"https://{configured_host}")
    except httpx.InvalidURL as exc:
        raise ValueError("Invalid Session.HOST") from exc
    if not url.raw_host:
        raise ValueError("Invalid Session.HOST")
    return url


def _cookie_host(configured_host):
    return _cookie_url(configured_host).raw_host.decode("ascii")


def _cookie_storage_host(host):
    url = httpx.URL(scheme="https", host=host)
    return eff_request_host(Request(str(url)))[1]


def _host_only_cookie_origin(domain, rest):
    if not isinstance(rest, dict):
        raise ValueError("Invalid authentication cookie origin")
    if _COOKIE_ORIGIN in rest:
        origin = rest[_COOKIE_ORIGIN]
        if not isinstance(origin, str) or not origin:
            raise ValueError("Invalid authentication cookie origin")
        try:
            url = httpx.URL(scheme="https", host=origin)
        except httpx.InvalidURL as exc:
            raise ValueError("Invalid authentication cookie origin") from exc
        if url.raw_host.decode("ascii") != origin or _cookie_host(str(url)) != origin:
            raise ValueError("Invalid authentication cookie origin")
    else:
        origin = _canonical_cookie_domain(domain)
        # Native single-label/IPv6 storage cannot reveal the original recipient.
        if domain != origin or (origin.endswith(".local") and origin.count(".") == 1):
            raise ValueError("Ambiguous authentication cookie origin")
    if domain != _cookie_storage_host(origin):
        raise ValueError("Invalid authentication cookie storage")
    return origin


class _OriginCookies(httpx.Cookies):
    def extract_cookies(self, response):
        jar = self.jar
        with jar._cookies_lock:
            before = {(cookie.domain, cookie.path, cookie.name): cookie for cookie in jar
                      if cookie.name in _AUTH_COOKIE_NAMES and not cookie.domain_specified}
            try:
                super().extract_cookies(response)
            finally:
                origin = response.request.url.raw_host.decode("ascii")
                for cookie in jar:
                    if cookie.name in _AUTH_COOKIE_NAMES and not cookie.domain_specified:
                        key = (cookie.domain, cookie.path, cookie.name)
                        if before.get(key) is not cookie:
                            cookie._rest[_COOKIE_ORIGIN] = origin


def _cookie_to_dict(cookie):
    return {
        "name": cookie.name,
        "value": cookie.value,
        "domain": cookie.domain,
        "path": cookie.path,
        "secure": cookie.secure,
        "expires": cookie.expires,
        "discard": cookie.discard,
        "domain_specified": cookie.domain_specified,
        "domain_initial_dot": cookie.domain_initial_dot,
        "path_specified": cookie.path_specified,
        "rest": cookie._rest,
    }


def _restore_cookie(data, configured_host):
    required = {"name", "value", "domain", "path"}
    optional = {
        "secure", "expires", "discard", "domain_specified",
        "domain_initial_dot", "path_specified", "rest",
    }
    if (
        not isinstance(data, dict)
        or not required <= data.keys()
        or data.keys() - required - optional
    ):
        raise ValueError("Invalid session cookies")
    name, value, domain, path = (
        data[key] for key in ("name", "value", "domain", "path")
    )
    if (
        not isinstance(name, str) or not name
        or (value is not None and not isinstance(value, str))
        or not isinstance(domain, str)
        or not isinstance(path, str) or not path.startswith("/")
    ):
        raise ValueError("Invalid session cookies")
    source_domain = _canonical_cookie_domain(domain)
    secure = data.get("secure", False)
    expires = data.get("expires")
    discard = data.get("discard", True)
    domain_specified = data.get("domain_specified", bool(domain))
    domain_initial_dot = data.get("domain_initial_dot", domain.startswith("."))
    path_specified = data.get("path_specified", True)
    rest = data.get("rest", {})
    if (
        any(type(flag) is not bool for flag in (
            secure, discard, domain_specified, domain_initial_dot, path_specified
        ))
        or (expires is not None and type(expires) is not int)
        or not isinstance(rest, dict)
        or any(
            not isinstance(key, str)
            or (item is not None and not isinstance(item, str))
            for key, item in rest.items()
        )
    ):
        raise ValueError("Invalid session cookies")

    if name in _AUTH_COOKIE_NAMES:
        host = _cookie_host(configured_host)
        if "domain_specified" in data and not domain_specified:
            if _host_only_cookie_origin(domain, rest) != host:
                raise ValueError("Invalid authentication cookie domain")
        else:
            if _COOKIE_ORIGIN in rest or (source_domain and source_domain != host and (
                source_domain.count(".") == 0 or not host.endswith("." + source_domain)
            )):
                raise ValueError("Invalid authentication cookie domain")
            domain = _cookie_storage_host(host)
            try:
                _host_only_cookie_origin(domain, rest)
            except ValueError:
                rest = {**rest, _COOKIE_ORIGIN: host}
        secure = True
        if domain_specified:
            domain_specified = False
            domain_initial_dot = False

    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=domain_specified,
        domain_initial_dot=domain_initial_dot,
        path=path,
        path_specified=path_specified,
        secure=secure,
        expires=expires,
        discard=discard,
        comment=None,
        comment_url=None,
        rest=rest,
        rfc2109=False,
    )


def _apply_cookies(session, cookies):
    auth_names = {cookie.name for cookie in cookies} & _AUTH_COOKIE_NAMES
    for cookie in list(session.cookies.jar):
        if cookie.name in auth_names:
            session.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)
    for cookie in cookies:
        session.cookies.jar.set_cookie(cookie)


def _validated_session_data(dumped, configured_host):
    if not isinstance(dumped, dict) or set(dumped) - set(Session._session_info):
        raise ValueError("Invalid session data")
    validated = {}
    for key, value in dumped.items():
        if key in {"eapi_config", "weapi_config", "login_info"}:
            if not isinstance(value, dict):
                raise ValueError("Invalid session data")
            validated[key] = value
        elif key == "csrf_token":
            if value is not None and not isinstance(value, str):
                raise ValueError("Invalid session data")
            validated[key] = value
        elif key == "cookies":
            if not isinstance(value, list):
                raise ValueError("Invalid session data")
            validated[key] = [_restore_cookie(item, configured_host) for item in value]
    return validated


def _apply_validated_session_data(session, validated):
    for key, value in validated.items():
        session._session_info[key][1](session, value)
    return True


def _invalid_serialized_session():
    raise ValueError("Invalid serialized session")


def _parse_session_data(dump, legacy_only=False):
    """Decode a bounded serialized session without constructing a client."""
    if not isinstance(dump, str) or len(dump) > _SESSION_STRING_MAX:
        _invalid_serialized_session()
    if legacy_only and dump.startswith("PYNCM"):
        _invalid_serialized_session()
    try:
        if dump.startswith("PYNCM"):
            encoded = dump[5:]
            compressed = base64.b64decode(encoded, validate=True)
            if base64.b64encode(compressed).decode("ascii") != encoded:
                _invalid_serialized_session()
            decoder = zlib.decompressobj()
            raw = decoder.decompress(compressed, _SESSION_JSON_MAX + 1)
            if (len(raw) > _SESSION_JSON_MAX or not decoder.eof
                    or decoder.unused_data or decoder.unconsumed_tail):
                _invalid_serialized_session()
        else:
            # ponytail: legacy AES still decrypts at most the fixed encoded-input cap.
            if (not dump or len(dump) % 32 or not dump.isascii()
                    or any(char not in "0123456789abcdefABCDEF" for char in dump)):
                _invalid_serialized_session()
            from .utils.crypto import EAPI_DIGEST_SALT
            from .utils import HashHexDigest

            plain = EapiDecrypt(HexCompose(dump)).decode("utf-8")
            delimiter = "-36cd479b6b5-"
            magic, separator, rest = plain.partition(delimiter)
            payload, last_separator, digest = rest.rpartition(delimiter)
            if (magic != "pyncm" or not separator or not last_separator
                    or not re.fullmatch(r"[0-9a-fA-F]{32}", digest)):
                _invalid_serialized_session()
            expected = HashHexDigest(EAPI_DIGEST_SALT % {"url": magic, "text": payload})
            if digest.lower() != expected:
                _invalid_serialized_session()
            raw = payload.encode("utf-8")
            if len(raw) > _SESSION_JSON_MAX:
                _invalid_serialized_session()

        def reject_constant(_value):
            raise ValueError("Invalid JSON constant")

        def parse_finite_float(value):
            result = float(value)
            if not math.isfinite(result):
                raise ValueError("Invalid JSON number")
            return result

        dumped = json.loads(raw.decode("utf-8"), parse_constant=reject_constant,
                            parse_float=parse_finite_float)
        return _validated_session_data(dumped, Session.HOST)
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error,
            zlib.error, RecursionError, AssertionError):
        pass
    _invalid_serialized_session()


def _snapshot_cookies(cookies):
    jar = cookies.jar if isinstance(cookies, httpx.Cookies) else cookies
    if isinstance(jar, CookieJar):
        with jar._cookies_lock:
            return httpx.Cookies(httpx.Cookies(jar))
    return httpx.Cookies(cookies)


class Session(httpx.AsyncClient):
    """# Session
        实现网易云音乐登录态 / API 请求管理

        - HTTP方面，`Session`的配置方法和 `httpx.Session` 完全一致，如配置 Headers:

        GetCurrentSession().headers['X-Real-IP'] = '1.1.1.1'

        - 该 Session 其他参数也可被修改:

        GetCurrentSession().force_http = True # 优先 HTTP

        - Session 对象本身可作为 Context Manager 使用:


    ```python
    # 利用全局 Session 完成该 API Call
    await LoginViaEmail(...)
    session = CreateNewSession() # 建立新的 Session
    async with session: # 进入该 Session, 在 `async with` 内的 API 将由该 Session 完成
        await LoginViaCellPhone(...)
    # 离开 Session. 此后 API 将继续由全局 Session 管理
    ```
    注：`async with` 的 Session 选择按 asyncio task context 隔离；子任务会继承
    Session 引用，但不延长其生命周期。

    获取其他具体信息请参考该文档注释
    """

    HOST = "music.163.com"
    """网易云音乐 API 服务器域名，可直接改为代理服务器之域名"""
    UA_DEFAULT = (
        f"Mozilla/5.0 (linux@github.com/mos9527/pyncm_asycn) Chrome/PyNCM_Async.{__version__}"
    )
    """Weapi 使用的 UA"""
    UA_EAPI = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 NeteaseMusicDesktop/2.10.2.200154"
    """EAPI 使用的 UA，不推荐更改"""
    UA_LINUX_API = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.90 Safari/537.36"
    """曾经的 Linux 客户端 UA，不推荐更改"""
    force_http = False
    """优先使用 HTTP 作 API 请求协议"""

    async def __aenter__(self) -> httpx.AsyncClient:
        entered = await super().__aenter__()
        self._session_context_token = _session_context.set(
            _session_context.get() + (self,)
        )
        self._session_context_owner = asyncio.current_task()
        return entered

    async def __aexit__(self, *args) -> None:
        stack = _session_context.get()
        if (
            getattr(self, "_session_context_owner", None) is not asyncio.current_task()
            or not stack
            or stack[-1] is not self
        ):
            raise RuntimeError("Session context must exit in its owning task and order")
        token = self._session_context_token
        try:
            return await super().__aexit__(*args)
        finally:
            _session_context.reset(token)
            self._session_context_token = None
            self._session_context_owner = None

    def __init__(self, *args, **kwargs):
        if isinstance(kwargs.get("cookies"), httpx.Cookies):
            kwargs["cookies"] = _snapshot_cookies(kwargs["cookies"])
        super().__init__(*args, **kwargs)
        self._cookies = _OriginCookies(self._cookies.jar)
        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": self.UA_DEFAULT,
            "Referer": self.HOST,
        }
        self.login_info = {"success": False, "tick": time(), "content": None}
        # https://gitlab.com/Binaryify/neteasecloudmusicapi/-/blob/main/util/request.js?ref_type=heads
        self.eapi_config = {
            "os": "iPhone OS",
            "appver": "10.0.0",
            "osver": "16.2",
            "channel": "distribution",
            "deviceId": DEVICE_ID_DEFAULT,
        }
        self.weapi_config = {
            "WEVNSM": "1.0.0",
            "sDeviceId": GenerateSDeviceId(),
            "WNMCID": GenerateWNMCID(),
        }
        self.csrf_token = ""

    @httpx.AsyncClient.cookies.setter
    def cookies(self, cookies):
        if isinstance(cookies, httpx.Cookies):
            cookies = _snapshot_cookies(cookies)
        httpx.AsyncClient.cookies.fset(self, cookies)
        self._cookies = _OriginCookies(self._cookies.jar)

    def _merge_cookies(self, cookies=None):
        merged = _snapshot_cookies(self.cookies)
        merged.update(_snapshot_cookies(cookies))
        merged.jar.set_policy(_CookiePolicy())
        # Passing a bare jar retains its policy through HTTPX's request construction.
        return merged.jar

    def _build_redirect_request(self, request, response):
        with self.cookies.jar._cookies_lock:
            redirected = super()._build_redirect_request(request, response)
            jar = _snapshot_cookies(self.cookies).jar
        redirected.headers.pop("Cookie", None)
        jar.set_policy(_CookiePolicy())
        httpx.Cookies(jar).set_cookie_header(redirected)
        return redirected

    # region Shorthands
    @property
    def deviceId(self):
        """设备 ID"""
        return self.eapi_config["deviceId"]

    @deviceId.setter
    def deviceId(self, value: str):
        self.eapi_config["deviceId"] = value

    @property
    def sDeviceId(self):
        return self.weapi_config["sDeviceId"]

    @sDeviceId.setter
    def sDeviceId(self, value: str):
        self.weapi_config["sDeviceId"] = value

    @property
    def uid(self):
        """用户 ID"""
        return self.login_info["content"]["account"]["id"] if self.logged_in else 0

    @property
    def nickname(self):
        """登陆用户的昵称"""
        return (
            self.login_info["content"]["profile"]["nickname"] if self.logged_in else ""
        )

    @property
    def lastIP(self):
        """登陆时，上一次登陆的 IP"""
        return (
            self.login_info["content"]["profile"]["lastLoginIP"]
            if self.logged_in
            else ""
        )

    @property
    def vipType(self):
        """账号 VIP 等级"""
        return (
            self.login_info["content"]["profile"]["vipType"]
            if self.logged_in and not self.is_anonymous
            else 0
        )

    @property
    def logged_in(self):
        """是否已经登陆"""
        return self.login_info["success"]

    @property
    def is_anonymous(self):
        """是否匿名登陆"""
        return self.logged_in and not self.nickname

    # endregion
    async def request(
        self, method: str, url: Union[str, bytes, Text], *args, **kwargs
    ) -> httpx.Response:
        """发起 HTTP(S) 请求
        该函数与 ` -> httpx.AsyncClient.request` 有以下不同：
        - 使用 SSL 与否取决于 `force_http`
        - 不强调协议（只用 HTTP(S)），不带协议的链接会自动补上 HTTP(S)

        Args:
            method (str): HTTP Verb
            url (Union[str, bytes, Text]): Complete/Partial HTTP URL

        Returns:
            httpx.Response
        """
        if url[:4] != "http":
            url = f"https://{self.HOST}{url}"
        if self.force_http:
            url = url.replace("https:", "http:")
        return await super().request(method, url, *args, **kwargs)

    # region symbols for loading/reloading authentication info
    _session_info = {
        "eapi_config": (
            lambda self: getattr(self, "eapi_config"),
            lambda self, v: setattr(self, "eapi_config", v),
        ),
        "weapi_config": (
            lambda self: getattr(self, "weapi_config"),
            lambda self, v: setattr(self, "weapi_config", v),
        ),
        "login_info": (
            lambda self: getattr(self, "login_info"),
            lambda self, v: setattr(self, "login_info", v),
        ),
        "csrf_token": (
            lambda self: getattr(self, "csrf_token"),
            lambda self, v: setattr(self, "csrf_token", v),
        ),
        "cookies": (
            lambda self: [_cookie_to_dict(c) for c in self.cookies.jar],
            lambda self, cookies: _apply_cookies(self, cookies),
        ),
    }

    def dump(self) -> dict:
        """以 `dict` 导出登录态"""
        return {
            name: self._session_info[name][0](self)
            for name in self._session_info.keys()
        }

    def load(self, dumped):
        """从 `dict` 加载登录态。

        Legacy/domain auth cookies migrate to secure host-only scope without widening paths.
        Already secure host-only cookies retain the stored flags, expiry and rest metadata.
        """
        validated = _validated_session_data(dumped, self.HOST)

        return _apply_validated_session_data(self, validated)


# endregion


class SessionManager:
    """PyNCM_Async Session 单例储存对象"""

    def __init__(self) -> None:
        self.session = Session()

    def get(self):
        stack = _session_context.get()
        if stack:
            return stack[-1]
        return self.session

    def set(self, session):
        if _session_context.get():
            raise Exception(
                "Current Session is in `with` block, which cannot be reassigned."
            )
        self.session = session

    # region Session serialization
    @staticmethod
    def stringify_legacy(session: Session) -> str:
        """（旧）序列化 `Session` 为 `str`"""
        return EapiEncrypt("pyncm", json.dumps(session.dump()))["params"]

    @staticmethod
    def parse_legacy(dump: str) -> Session:
        """（旧）反序列化 `str` 为 `Session`"""
        data = _parse_session_data(dump, legacy_only=True)
        session = Session()
        _apply_validated_session_data(session, data)
        return session

    @staticmethod
    def stringify(session: Session) -> str:
        """序列化 `Session` 为 `str`"""
        from json import dumps
        from zlib import compress
        from base64 import b64encode

        return "PYNCM" + b64encode(compress(dumps(session.dump()).encode())).decode()

    @staticmethod
    def parse(dump: str) -> Session:
        """反序列化 `str` 为 `Session`"""
        data = _parse_session_data(dump)
        session = Session()
        _apply_validated_session_data(session, data)
        return session


# endregion

sessionManager = SessionManager()


def GetCurrentSession() -> Session:
    """获取当前正在被 PyNCM_Async 使用的 Session / 登录态"""
    return sessionManager.get()


def SetCurrentSession(session: Session):
    """设置当前正在被 PyNCM_Async 使用的 Session / 登录态"""
    sessionManager.set(session)


def SetNewSession():
    """设置新的被 PyNCM_Async 使用的 Session / 登录态"""
    sessionManager.set(Session())


def CreateNewSession() -> Session:
    """创建新 Session 实例"""
    return Session()


def LoadSessionFromString(dump: str) -> Session:
    """从 `str` 加载 Session / 登录态"""
    session = SessionManager.parse(dump)
    return session


def DumpSessionAsString(session: Session) -> str:
    """从 Session / 登录态 导出 `str`"""
    return SessionManager.stringify(session)


def WriteLoginInfo(content: dict):
    """写登录态入Session

    Args:
        content (dict): 解码后的登录态

    Raises:
        LoginFailedException: 登陆失败时发生
    """
    _write_login_info(GetCurrentSession(), content)


def _write_login_info(session, content):
    session.login_info = {"tick": time(), "content": content}
    code = content.get("code") if isinstance(content, dict) else None
    if code != 200:
        session.login_info["success"] = False
        safe_code = code if type(code) is int else "unknown"
        raise Exception(f"Login failed (code: {safe_code})")
    session.login_info["success"] = True
    session.csrf_token = session.cookies.get("__csrf")
