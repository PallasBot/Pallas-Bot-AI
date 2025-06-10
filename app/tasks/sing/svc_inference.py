import os
import platform
from pathlib import Path

from pydub import AudioSegment

from app.core.config import settings
from app.utils.gpu_locker import GPULockManager

DDSP = (Path(__file__).parent / "DDSP-SVC" / "main_reflow.py").absolute()
SVC_OUPUT_FORMAT = "flac"


def inference(song_path: Path, output_dir: Path, key: int = 0, speaker: str = "pallas", locker: GPULockManager = None):
    if platform.system() == "Windows":
        song_path = mp3_to_wav(song_path)

    stem = song_path.stem
    result = output_dir / f"{stem}_{key}key_{speaker}_ddsp.{SVC_OUPUT_FORMAT}"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not result.exists():
        # speaker_models = {}

        # if speaker not in speaker_models:
        #     models_dir = Path(f"resource/sing/models/{speaker}/")
        #     for m in models_dir.iterdir():
        #         if m.name.startswith("G_") and m.name.endswith(".pth"):
        #             speaker_models[speaker] = m
        #             break

        dm_current_path = Path(f"resource/sing/models/{speaker}/{speaker}.pt")

        # if speaker not in speaker_models:
        #     print("'{speaker}'s .pth not found")
        #     return None

        cmd = ""
        if settings.sing_cuda_device:
            if platform.system() == "Windows":
                cmd = f"set CUDA_VISIBLE_DEVICES={settings.sing_cuda_device} && "
            else:
                cmd = f"CUDA_VISIBLE_DEVICES={settings.sing_cuda_device} "

        cmd += (
            f"python {DDSP} -i {song_path.absolute()} -m {dm_current_path.absolute()} -o {result.absolute()} -k {key}"
        )

        try:
            with locker.acquire():
                print(cmd)
                os.system(cmd)
        except Exception as e:
            print(e)

    if not result.exists():
        return None

    return result


def mp3_to_wav(mp3_file_path: Path) -> Path:
    wav_file_path = mp3_file_path.parent / (mp3_file_path.stem + ".wav")

    if wav_file_path.exists():
        return wav_file_path

    sound = AudioSegment.from_mp3(mp3_file_path)
    sound.export(wav_file_path, format="wav")
    # os.remove(mp3_file_path)
    return Path(wav_file_path)
