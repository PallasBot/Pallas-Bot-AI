from __future__ import annotations

import pytest

from app.providers.operator_lookup import extract_operator_lookup_name, strip_cq_codes


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("你知道谁是银灰吗", "银灰"),
        ("银灰是谁", "银灰"),
        ("谁是银灰", "银灰"),
        ("介绍一下能天使", "能天使"),
        ("说说推进之王", "推进之王"),
        ("[CQ:at,qq=123] 你知道谁是银灰吗", "银灰"),
        ("你是谁", ""),
        ("我又是谁", ""),
        ("你知道你是谁吗", ""),
        ("@渡月桥 你是谁", ""),
        ("", ""),
        ("今天天气不错", ""),
    ],
)
def test_extract_operator_lookup_name(text: str, expected: str) -> None:
    assert extract_operator_lookup_name(text) == expected


def test_strip_cq_codes() -> None:
    assert strip_cq_codes("[CQ:face,id=123] 你好") == "你好"
