import json
import os
import platform
from pathlib import Path
from threading import Lock

from loguru import logger
from pydub import AudioSegment

from app.utils.gpu_locker import GPULockManager

SVC_MAIN_41 = (Path(__file__).parent / 'so_vits_svc_41' / 'inference_main.py').absolute()
SVC_MAIN_40 = (Path(__file__).parent / 'so_vits_svc' / 'inference_main.py').absolute()
DDSP = (Path(__file__).parent / 'DDSP-SVC' / 'main_reflow.py').absolute()
SVC_HUBERT = Path('resource/sing/models/checkpoint_best_legacy_500.pt').absolute()
SVC_CHECK = Path('src/plugins/sing/so_vits_svc_41/pretrain/checkpoint_best_legacy_500.pt').absolute()
SVC_SLICE_DB = -30
SVC_FORCE_SLICE = 40    # 实际推理时的最大切片长度，单位：秒。
# 越大越吃显存，速度会稍微快一点点。
# 但如果切得太小，连接处有可能有瑕疵（其实影响也不大
SVC_OUPUT_FORMAT = 'flac'
SVC_PATH = os.path.join(os.getcwd(), 'resource\\sing\\svc')
cuda_devices = ''


def set_svc_cuda_devices(devices: str):
    global cuda_devices
    cuda_devices = devices


def set_svc_force_slice(secs: int):
    global SVC_FORCE_SLICE
    SVC_FORCE_SLICE = secs


speaker_models = {}


def inference(song_path: Path, output_dir: Path, key: int = 0, speaker: str = "pallas", locker: GPULockManager = None):
    # 这个库不知道咋集成，似乎可以转成 ONNX，但是我不会
    # 先用 cmd 凑合跑了
    # TODO: 使用 ONNX Runtime 重新集成

    if platform.system() == "Windows":
        song_path = mp3_to_wav(song_path)

    stem = song_path.stem
    result = output_dir / \
        f'{SVC_PATH}\\{stem}_{key}key_{speaker}_sovits_pm.{SVC_OUPUT_FORMAT}'

    if not result.exists():
        global speaker_models

        model = ""
        if speaker not in speaker_models:
            models_dir = Path(f'resource/sing/models/{speaker}/')
            for m in os.listdir(models_dir):
                if m.startswith('G_') and m.endswith('.pth'):
                    speaker_models[speaker] = models_dir / m
                    break
            for d_m in os.listdir(models_dir):
                if d_m.endswith('.pt'):
                    dm_Path = models_dir / d_m
                    break
            for d_c in os.listdir(models_dir):
                if d_c.endswith('.yaml'):
                    dc_Path = models_dir / d_c
                    break

        config_json = Path(f'resource/sing/models/{speaker}/config.json').absolute()
        dm_current_path = Path(f'resource/sing/models/{speaker}/{speaker}.pt').absolute()
        dc_current_path = Path(f'esource/sing/models/{speaker}/diffusion.yaml').absolute()
        if os.path.exists(dc_current_path) and os.path.exists(dm_current_path):
            flag = 1
        else:
            flag = 0
        logger.info(f"未检测到浅扩散模型，若想使用请将 .pt 与 .yaml 放于model文件夹下")

        global svc_edition
        svc_edition = 1
        try:
            with open(f"{config_json}", "r", encoding="utf-8") as file:
                json_str = file.read()
                data = json.loads(json_str)
                gin = data["model"]["gin_channels"]
                if gin == 768:
                    svc_edition = 1
                    result = output_dir / \
                        f'{SVC_PATH}\\{stem}_{key}key_{speaker}_sovits_pm.{SVC_OUPUT_FORMAT}'
                else:
                    svc_edition = 0
                    result = output_dir / \
                        f'{stem}_{key}key_{speaker}.{SVC_OUPUT_FORMAT}'
        except FileNotFoundError:
            svc_edition = 1
            result = output_dir / \
                f'{stem}_{key}key_{speaker}_ddsp.{SVC_OUPUT_FORMAT}'
            output_dir = output_dir / \
                f'{stem}_{key}key_{speaker}_ddsp.{SVC_OUPUT_FORMAT}'
            flag = 2
            print("'{speaker}'s config.pt not found")
        try:
            model = speaker_models[speaker].absolute()
        except KeyError:
            print("'{speaker}'s .pth not found")

        if flag == 1 or flag == 0:

            if not os.path.exists(model):
                print("!!! G Model not found !!!", model)
                return None
            if not os.path.exists(config_json):
                print("!!! Config not found !!!", config_json)
                return None
            if svc_edition == 1:
                if not os.path.exists(SVC_CHECK):
                    print("!!! Hubert model not found !!!", SVC_CHECK)
                    return None
            else:
                if not os.path.exists(SVC_HUBERT):
                    print("!!! Hubert model not found !!!", SVC_HUBERT)
                    return None

        cmd = ''
        if cuda_devices:
            if platform.system() == 'Windows':
                cmd = f'set CUDA_VISIBLE_DEVICES={cuda_devices} && '
            else:
                cmd = f'CUDA_VISIBLE_DEVICES={cuda_devices} '

        if svc_edition == 1:

            if flag == 1:
                cmd += f'python {SVC_MAIN_41} -m {model} -c {config_json} -dm {dm_current_path} -dc {dc_current_path} \
                    -n {song_path.absolute()} -t {key} -s {speaker} '
            if flag == 0:
                cmd += f'python {SVC_MAIN_41} -m {model} -c {config_json} \
                    -n {song_path.absolute()} -t {key} -s {speaker} '
            if flag == 2:
                cmd += f'python {DDSP}  -i {song_path.absolute()} -m {dm_current_path.absolute()} -o {output_dir.absolute()}'

        else:
            cmd += f'python {SVC_MAIN_40} -m {model} -c {config_json} -hb {SVC_HUBERT.absolute()} \
                -f {song_path.absolute()} -t {key} -s {speaker} -sd {SVC_SLICE_DB} -sf {SVC_FORCE_SLICE}\
                -o {output_dir.absolute()} -wf {SVC_OUPUT_FORMAT}'

        try:
            with locker.acquire():
                print(cmd)
                os.system(cmd)
        except Exception as e:
            print(e)

    if not result.exists():
        return None

    return result


def mp3_to_wav(mp3_file_path):
    mp3_dirname, mp3_filename = os.path.split(mp3_file_path)
    wav_filename = os.path.splitext(mp3_filename)[0] + '.wav'
    wav_file_path = os.path.join(mp3_dirname, wav_filename)

    if os.path.exists(wav_file_path):
        return Path(wav_file_path)

    sound = AudioSegment.from_mp3(mp3_file_path)
    sound.export(wav_file_path, format="wav")
    # os.remove(mp3_file_path)
    return Path(wav_file_path)
