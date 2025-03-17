import shutil
from pathlib import Path

from pydub import AudioSegment


def mix(vocals: Path, no_vocals: Path, origin_vocals: Path, output_dir: Path, output_stem: str, extension: str = "mp3"):
    path = output_dir / f"{output_stem}.{extension}"
    if path.exists():
        return path

    if not vocals.exists() or not no_vocals.exists():
        return None

    # 自动增益
    origin_vocals_audio = AudioSegment.from_file(origin_vocals)
    origin_db = origin_vocals_audio.dBFS
    vocals_audio = AudioSegment.from_file(vocals)
    vocals_db = vocals_audio.dBFS
    vocals_audio = vocals_audio.apply_gain(origin_db - vocals_db)

    # 混合
    no_vocals_audio = AudioSegment.from_file(no_vocals)
    mix_audio = vocals_audio.overlay(no_vocals_audio)

    # 保存
    output_dir.mkdir(parents=True, exist_ok=True)
    mix_audio.export(path, format=extension)

    if not path.exists():
        return None

    return path


def splice(
    input_song: Path,
    output_dir: Path,
    finished: bool,
    song_id: str,
    chunk_index: int,
    speaker: str,
    key: int = 0,
    format: str = "mp3",
):
    output_dir.mkdir(parents=True, exist_ok=True)
    # os.makedirs(output_dir)
    # 随机播放的时候要根据文件名判断进度，这个文件名之后改的话要注意下
    last_file_path = output_dir / f"{song_id}_spliced{chunk_index - 1}_{key}key_{speaker}.{format}"
    now_file_path = output_dir / f"{song_id}_spliced{chunk_index}_{key}key_{speaker}.{format}"

    if finished:
        now_file_path = output_dir / f"{song_id}_full_{key}key_{speaker}.{format}"

    if chunk_index == 0:
        if input_song.exists() and not now_file_path.exists():
            shutil.copy(input_song, now_file_path)
        return now_file_path

    # 不是第一段且没有能接的文件，过
    if not last_file_path.exists():
        return now_file_path

    # 合并
    print("splicing audio...")
    output_audio = AudioSegment.from_file(last_file_path)
    if input_song.exists():
        output_audio += AudioSegment.from_file(input_song)
    # 保存
    output_audio.export(now_file_path, format=format)

    last_file_path.unlink()

    return now_file_path
