from pathlib import Path

from pyncm import apis as ncm

from app.utils.download_tool import DownloadTools

# if settings.ncm_phone and settings.ncm_password:
#     ncm.login.LoginViaCellphone(phone=settings.ncm_phone, password=settings.ncm_password, ctcode=settings.ncm_ctcode)
# elif settings.ncm_email and settings.ncm_password:
#     ncm.login.LoginViaEmail(email=settings.ncm_email, password=settings.ncm_password)
# else:
#     ncm.login.LoginViaAnonymousAccount()

ncm.login.LoginViaAnonymousAccount()


def download(song_id):
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
    response = ncm.track.GetTrackAudio(song_id)
    if response["data"][0]["size"] > 100000000:  # 100MB
        return None
    return response["data"][0]["url"]


def request_file(url):
    return DownloadTools.request_file(url)


def get_song_title(song_id):
    response = ncm.track.GetTrackDetail(song_id)
    return response["songs"][0]["name"]


def get_song_id(song_name: str):
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
