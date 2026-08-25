import time
import traceback

import requests

from app.core.logger import logger

_session = requests.Session()
_session.trust_env = False


class DownloadTools:
    @staticmethod
    def request_file(url, stringify=False, timeout=120):
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) "
            "AppleWebKit/603.1.30 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1"
        }
        # noinspection PyBroadException
        try:
            stream = _session.get(url, headers=headers, stream=True, timeout=(10, 20))
            if stream.status_code == 200:
                start = time.monotonic()
                chunks = []
                for chunk in stream.iter_content(chunk_size=65536):
                    if time.monotonic() - start > timeout:
                        logger.error("download request timed out: url={} limit={}s", url, timeout)
                        return None
                    if chunk:
                        chunks.append(chunk)
                if stringify:
                    return b"".join(chunks).decode(encoding="utf-8")
                return b"".join(chunks)
        except Exception:
            logger.error("download request failed: url={}\n{}", url, traceback.format_exc())
        return None
