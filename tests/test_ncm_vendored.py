import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import pyncm_async
from pyncm_async.apis.cloud import SetUploadObject


def test_import_uses_sidecar_copy() -> None:
    package = Path(pyncm_async.__file__).resolve().parent
    assert package == Path(__file__).resolve().parents[1] / "pyncm_async"


def test_cloud_upload_fails_closed_without_http() -> None:
    session = AsyncMock()
    with pytest.raises(NotImplementedError, match="unencrypted HTTP"):
        asyncio.run(
            SetUploadObject(
                b"synthetic audio",
                "synthetic-md5",
                16,
                "synthetic-key",
                "synthetic-token",
                session=session,
            )
        )
    session.post.assert_not_called()
