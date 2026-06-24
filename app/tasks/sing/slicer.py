from pathlib import Path

from pydub import AudioSegment


def slice_audio(path: Path, output_dir: Path, output_stem: str, audio_format: str = "mp3", size_ms: int = 40000):
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_segment = AudioSegment.from_file(path, format=audio_format)
    total = int(audio_segment.duration_seconds * 1000 / size_ms)  # 计算音频切片后的个数

    results = [output_dir / f"{output_stem}_chunk{i}.{audio_format}" for i in range(total + 1)]
    if all(f.exists() for f in results):
        return results

    print("splitting audio...")
    for i in range(total + 1):
        chunk = audio_segment[i * size_ms : (i + 1) * size_ms]
        chunk.export(results[i], format=audio_format)

    return results
