from pathlib import Path

from pyncm_async import apis as ncm

from app.tasks.sing.ncm_login import ncm_request_session
from app.utils.download_tool import DownloadTools


async def download(song_id):
    folder = Path("resource/sing/ncm")
    path = folder / f"{song_id}.mp3"
    if path.exists():
        return path

    async with ncm_request_session():
        response = await ncm.track.GetTrackAudio(song_id)
        if response["data"][0]["size"] > 100000000:
            return None
        url = response["data"][0]["url"]

    content = request_file(url)
    if not content:
        return None

    folder.mkdir(exist_ok=True)
    with path.open(mode="wb+") as voice:
        voice.write(content)

    return path


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
