import hashlib
import random
import time
import uuid

import requests

from app.core.config import settings


class BaiduTranslator:
    def __init__(self, app_id, secret_key):
        self.app_id = app_id
        self.secret_key = secret_key
        self.url = "http://api.fanyi.baidu.com/api/trans/vip/translate"

    def translate(self, text, from_lang="zh", to_lang="jp"):
        salt = random.randint(32768, 65536)
        sign_str = self.app_id + text + str(salt) + self.secret_key
        sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()

        params = {
            "q": text,
            "from": from_lang,
            "to": to_lang,
            "appid": self.app_id,
            "salt": salt,
            "sign": sign,
        }

        try:
            response = requests.get(self.url, params=params, timeout=5)
            result = response.json()

            if "trans_result" in result:
                return result["trans_result"][0]["dst"]
            else:
                print(f"翻译出错: {result}")
                return text  # 出错时返回原文
        except Exception as e:
            print(f"翻译请求异常: {e}")
            return text  # 异常时返回原文


class YoudaoTranslator:
    def __init__(self, app_key, app_secret):
        self.app_key = app_key
        self.app_secret = app_secret
        self.url = "https://openapi.youdao.com/api"

    def translate(self, text, from_lang="zh-CHS", to_lang="ja"):
        salt = str(uuid.uuid1())
        curtime = str(int(time.time()))
        sign = self._calculate_sign(text, salt, curtime)

        params = {
            "q": text,
            "from": from_lang,
            "to": to_lang,
            "appKey": self.app_key,
            "salt": salt,
            "sign": sign,
            "signType": "v3",
            "curtime": curtime,
        }

        try:
            response = requests.post(self.url, data=params, timeout=5)
            result = response.json()

            if result.get("errorCode") == "0" and "translation" in result:
                return result["translation"][0]
            else:
                print(f"翻译出错: {result}")
                return text  # 出错时返回原文
        except Exception as e:
            print(f"翻译请求异常: {e}")
            return text  # 异常时返回原文

    def _calculate_sign(self, q, salt, curtime):
        input_str = self._get_input(q)
        sign_str = self.app_key + input_str + salt + curtime + self.app_secret
        hash_algorithm = hashlib.sha256()
        hash_algorithm.update(sign_str.encode("utf-8"))
        return hash_algorithm.hexdigest()

    def _get_input(self, text):
        if text is None:
            return text
        text_len = len(text)
        return text if text_len <= 20 else text[0:10] + str(text_len) + text[text_len - 10 : text_len]


BAIDU_APP_ID = settings.baidu_app_id
BAIDU_SECRET_KEY = settings.baidu_secret_key

baidu_translator = BaiduTranslator(BAIDU_APP_ID, BAIDU_SECRET_KEY)


YOUDAO_APP_KEY = settings.youdao_app_key
YOUDAO_APP_SECRET = settings.youdao_app_secret

youdao_translator = YoudaoTranslator(YOUDAO_APP_KEY, YOUDAO_APP_SECRET)

# 默认使用百度翻译
active_translator = settings.default_translator
if active_translator == "baidu":
    active_translator = baidu_translator
elif active_translator == "youdao":
    active_translator = youdao_translator
