from pathlib import Path

from app.windows_compat import configure_windows_compatibility


def test_configure_windows_compatibility_patches_dependencies_and_isolates_jit_cache(tmp_path: Path) -> None:
    site_packages = tmp_path / "site-packages"
    cloud_py = site_packages / "pyncm_async" / "apis" / "cloud.py"
    cloud_py.parent.mkdir(parents=True)
    cloud_py.write_text('url = f"{objectKey.replace("/", "%2F")}"\n', encoding="utf-8")

    rwkv_model = site_packages / "rwkv" / "model.py"
    rwkv_model.parent.mkdir()
    rwkv_model.write_text('flags = ["-Xptxas -O3"]\n', encoding="utf-8")

    env = {"_CL_": "/O2"}
    changed = configure_windows_compatibility(
        env=env,
        site_packages=[site_packages],
        argv=["python", "-m", "celery"],
        cwd=tmp_path,
        system="Windows",
    )

    assert changed is True
    assert "objectKey.replace('/', '%2F')" in cloud_py.read_text(encoding="utf-8")
    assert '"-Xptxas", "-O3"' in rwkv_model.read_text(encoding="utf-8")
    assert env["_CL_"] == "/O2 /Zc:preprocessor"
    assert env["TORCH_EXTENSIONS_DIR"] == str(tmp_path / ".torch_extensions" / "celery")


def test_configure_windows_compatibility_leaves_non_windows_unchanged(tmp_path: Path) -> None:
    env = {}

    changed = configure_windows_compatibility(
        env=env,
        site_packages=[tmp_path],
        argv=["python", "-m", "uvicorn"],
        cwd=tmp_path,
        system="Linux",
    )

    assert changed is False
    assert env == {}
