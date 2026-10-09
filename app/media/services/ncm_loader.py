from pathlib import Path

from app.core.logger import logger
from app.media.services.ncm_login import ncm_request_session
from app.utils.download_tool import DownloadTools
from pyncm_async import apis as ncm


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


async def get_song_detail(song_id):
    async with ncm_request_session():
        response = await ncm.track.GetTrackDetail(song_id)
    songs = response.get("songs") if isinstance(response, dict) else None
    if not isinstance(songs, list) or not songs or not isinstance(songs[0], dict):
        return None

    song = songs[0]
    name = str(song.get("name") or "").strip()
    if not name:
        return None
    raw_artists = song.get("ar")
    artists = (
        [
            str(artist.get("name") or "").strip()
            for artist in raw_artists
            if isinstance(artist, dict) and str(artist.get("name") or "").strip()
        ]
        if isinstance(raw_artists, list)
        else []
    )
    return {"name": name, "artists": artists}


async def get_song_title(song_id):
    detail = await get_song_detail(song_id)
    return detail["name"] if detail else None


async def get_song_id(song_name: str, *, exclude_vip: bool = True):
    if not song_name:
        return None

    async with ncm_request_session():
        res = await ncm.cloudsearch.GetSearchResult(song_name, 1, 10)

    result = res.get("result") if isinstance(res, dict) else None
    if not isinstance(result, dict) or not result.get("songCount"):
        return None

    songs = result.get("songs")
    if not isinstance(songs, list):
        return None

    for song in songs:
        if not isinstance(song, dict):
            continue
        if exclude_vip:
            privilege = song.get("privilege")
            charge_info_list = privilege.get("chargeInfoList") if isinstance(privilege, dict) else None
            if not isinstance(charge_info_list, list) or not charge_info_list:
                continue
            if not isinstance(charge_info_list[0], dict) or charge_info_list[0].get("chargeType") == 1:
                continue
        if song.get("id") is not None:
            return song["id"]

    return None
