from app.core.logger import logger
from app.schemas.llm_chat import LlmChatCompletionRequest, LlmChatMessage
from app.services.llm_chat import submit_llm_chat_completion
from app.tasks.chat import ChatManager


async def chat(request_id: str, session: str, text: str, token_count: int, tts: bool):
    logger.info("legacy chat bridge: request_id={} session={}", request_id, session)
    return await submit_llm_chat_completion(
        request_id,
        LlmChatCompletionRequest(
            session_id=session,
            system="你是牛牛。",
            messages=[LlmChatMessage(role="user", content=text)],
            metadata={
                "task": "drunk",
                "token_count": token_count,
                "tts": tts,
                "mode": "drunk",
            },
        ),
    )


async def del_session(session: str):
    ChatManager.del_session(session)
