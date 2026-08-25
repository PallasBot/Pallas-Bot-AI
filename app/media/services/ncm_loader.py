from pathlib import Path

from pyncm_async import apis as ncm

from app.core.logger import logger
from app.media.services.ncm_login import ncm_request_session
from app.utils.download_tool import DownloadTools


async def download(song_id):
    folder = Path("resource/sing/ncm")
    path = folder / f"{song_id}.mp3"
    if path.exists():
        return path

    url = None
    for _ in range(3):
        async with ncm_request_session():
            response = await ncm.track.GetTrackAudio(song_id)
            if response["data"][0]["size"] > 100000000:
                return None
            url = response["data"][0]["url"]

        content = request_file(url)
        if not content:
            continue

        # 校验确实是可播放的音频：网易 CDN 不稳时可能返回错误体/失效链接
        if not _looks_like_audio(content):
            continue

        folder.mkdir(exist_ok=True)
        with path.open(mode="wb+") as voice:
            voice.write(content)

        return path

    if url:
        logger.error(
            "ncm download failed after retries: song_id={} last_url={}",
            song_id,
            url,
        )
    return None


def _looks_like_audio(content: bytes) -> bool:
    magic = content[:4]
    return (
        magic.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"fLaC", b"OggS", b"RIFF"))
        or content[:10] == b"\x00\x00\x00\x18ftyp"  # m4a
    )


def request_file(url):
    return DownloadTools.request_file(url)


async def get_song_title(song_id):
    async with ncm_request_session():
        response = await ncm.track.GetTrackDetail(song_id)
        return response["songs"][0]["name"]


async def get_song_id(song_name: str):
    if not song_name:
        return None

    async with ncm_request_session():
        res = await ncm.cloudsearch.GetSearchResult(song_name, 1, 10)

    if "result" not in res or "songCount" not in res["result"]:
        return None

    if res["result"]["songCount"] == 0:
        return None

    for song in res["result"]["songs"]:
        privilege = song["privilege"]
        if "chargeInfoList" not in privilege:
            continue

        charge_info_list = privilege["chargeInfoList"]
        if len(charge_info_list) == 0:
            continue

        if charge_info_list[0]["chargeType"] == 1:
            continue

        return song["id"]

    return None
