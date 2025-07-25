from pathlib import Path

from pyncm import SetCurrentSession
from pyncm import apis as ncm

from app.tasks.sing.ncm_login import ncm_login_manager
from app.utils.download_tool import DownloadTools


def download(song_id):
    # 确保使用登录session
    ensure_session()

    folder = Path("resource/sing/ncm")
    path = folder / f"{song_id}.mp3"
    if path.exists():
        return path

    url = get_audio_url(song_id)
    if not url:
        return None

    content = request_file(url)
    if not content:
        return None

    folder.mkdir(exist_ok=True)
    with path.open(mode="wb+") as voice:
        voice.write(content)

    return path


def get_audio_url(song_id):
    ensure_session()

    response = ncm.track.GetTrackAudio(song_id)
    if response["data"][0]["size"] > 100000000:  # 100MB
        return None
    return response["data"][0]["url"]


def request_file(url):
    return DownloadTools.request_file(url)


def get_song_title(song_id):
    ensure_session()

    response = ncm.track.GetTrackDetail(song_id)
    return response["songs"][0]["name"]


def get_song_id(song_name: str):
    ensure_session()

    if not song_name:
        return None

    res = ncm.cloudsearch.GetSearchResult(song_name, 1, 10)
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


def ensure_session():
    session = ncm_login_manager.session
    if session:
        # 设置当前session为登录的session
        SetCurrentSession(session)
    else:
        pass
