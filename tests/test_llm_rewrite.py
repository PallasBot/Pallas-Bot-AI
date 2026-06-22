from __future__ import annotations

import asyncio

from app.services.llm_rewrite import maybe_rewrite_llm_reply, rewrite_llm_reply


def test_maybe_rewrite_llm_reply_passthrough() -> None:
    reply = asyncio.run(maybe_rewrite_llm_reply("你好", metadata={"task": "llm_chat"}))
    assert reply == "你好"


def test_maybe_rewrite_llm_reply_trims_servicey_phrases() -> None:
    reply = asyncio.run(maybe_rewrite_llm_reply("总的来说，这个可以。希望这能帮到你", metadata={"task": "llm_chat"}))
    assert "总的来说" not in reply
    assert "希望这能帮到你" not in reply
    assert reply == "这个可以。"


def test_maybe_rewrite_llm_reply_avoids_repeated_leading_filler() -> None:
    reply = asyncio.run(
        maybe_rewrite_llm_reply(
            "其实这事就这样",
            metadata={"variation_hint": "【本轮表达去重】\n- 最近几轮别再用这些开头：其实、感觉"},
        )
    )
    assert reply == "这事就这样"


def test_maybe_rewrite_llm_reply_trims_repeated_laugh_opener() -> None:
    reply = asyncio.run(
        maybe_rewrite_llm_reply(
            "哈哈，别这么正式啦，叫我牛牛就行。",
            metadata={"variation_hint": "【本轮表达去重】\n- 最近几轮别再用这些开头：哈哈类"},
        )
    )
    assert reply == "别这么正式啦，叫我牛牛就行。"


def test_maybe_rewrite_llm_reply_trims_repeated_sigh_opener() -> None:
    reply = asyncio.run(
        maybe_rewrite_llm_reply(
            "欸，这也太巧了吧。",
            metadata={"variation_hint": "【本轮表达去重】\n- 最近几轮别再用这些开头：语气词类"},
        )
    )
    assert reply == "这也太巧了吧。"


def test_maybe_rewrite_llm_reply_trims_repeated_generic_opener() -> None:
    reply = asyncio.run(
        maybe_rewrite_llm_reply(
            "行吧，那就先这样。",
            metadata={"variation_hint": "【本轮表达去重】\n- 最近几轮别再用这些开头：行吧"},
        )
    )
    assert reply == "那就先这样。"


def test_maybe_rewrite_llm_reply_trims_overexplaining_when_hint_requests_shorter() -> None:
    reply = asyncio.run(
        maybe_rewrite_llm_reply(
            "这事可以做，不过得先把前面的状态收一收。后面再补细节也来得及。",
            metadata={"task": "repeater_polish", "variation_hint": "【本轮表达去重】\n- 最近解释偏满，这轮优先短一点，像顺手接一句"},
        )
    )
    assert reply == "这事可以做，不过得先把前面的状态收一收。"


def test_maybe_rewrite_llm_reply_softens_template_ending() -> None:
    reply = asyncio.run(
        maybe_rewrite_llm_reply(
            "先这么办吧，大概就是这样。",
            metadata={"variation_hint": "【本轮表达去重】\n- 最近收尾太像模板，换个自然收口"},
        )
    )
    assert reply == "先这么办吧，大概就这样。"


def test_rewrite_llm_reply_reports_applied_rules() -> None:
    result = asyncio.run(
        rewrite_llm_reply(
            "其实总的来说，这事可以做。不过得先把前面的状态收一收。大概就是这样。",
            metadata={
                "variation_hint": (
                    "【本轮表达去重】\n"
                    "- 最近几轮别再用这些开头：其实、感觉\n"
                    "- 最近解释偏满，这轮优先短一点，像顺手接一句\n"
                    "- 最近收尾太像模板，换个自然收口"
                )
            },
        )
    )
    assert result.reply == "这事可以做。不过得先把前面的状态收一收。"
    assert result.applied_rules == (
        "trim_servicey_phrase",
        "avoid_repeated_opener",
        "trim_overexplaining",
    )


def test_rewrite_llm_reply_reports_template_ending_rule() -> None:
    result = asyncio.run(
        rewrite_llm_reply(
            "先这么办吧，大概就是这样。",
            metadata={"variation_hint": "【本轮表达去重】\n- 最近收尾太像模板，换个自然收口"},
        )
    )
    assert result.reply == "先这么办吧，大概就这样。"
    assert result.applied_rules == (
        "soften_template_ending",
    )


def test_rewrite_llm_reply_adapts_length_only_for_llm_chat() -> None:
    result = asyncio.run(
        rewrite_llm_reply(
            "这事可以做，不过得先把前面的状态收一收。",
            metadata={
                "task": "llm_chat",
                "variation_hint": "【本轮表达去重】\n- 最近解释偏满，这轮优先短一点，像顺手接一句",
            },
        )
    )
    assert result.reply == "这事可以做。"
    assert result.applied_rules == (
        "adapt_llm_chat_length",
    )


def test_rewrite_llm_reply_does_not_adapt_length_for_repeater_tasks() -> None:
    result = asyncio.run(
        rewrite_llm_reply(
            "这事可以做，不过得先把前面的状态收一收。",
            metadata={
                "task": "repeater_polish",
                "variation_hint": "【本轮表达去重】\n- 最近解释偏满，这轮优先短一点，像顺手接一句",
            },
        )
    )
    assert result.reply == "这事可以做，不过得先把前面的状态收一收。"
    assert result.applied_rules == ()


def test_rewrite_llm_reply_trims_ai_scaffold_but_keeps_emotion_for_llm_chat() -> None:
    result = asyncio.run(
        rewrite_llm_reply(
            "你这波也太黑了，不过没事，先别急，我感觉大概率还是前面节奏没踩稳。总的来说先缓一缓。",
            metadata={
                "task": "llm_chat",
                "variation_hint": (
                    "【本轮表达去重】\n"
                    "- 最近解释偏满，这轮优先短一点，像顺手接一句\n"
                    "- 最近句式有点一个模子，少用“先判断一下、再补解释”的答法"
                ),
            },
        )
    )
    assert result.reply == "你这波也太黑了，先缓一缓。"
    assert "你这波也太黑了" in result.reply
    assert result.applied_rules == (
        "trim_servicey_phrase",
        "adapt_llm_chat_length",
        "trim_llm_chat_scaffold",
    )
