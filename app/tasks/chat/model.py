import os
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Lock

import torch

os.environ["RWKV_V7_ON"] = "1"
os.environ["RWKV_JIT_ON"] = "1"
# 这个要配个 ninja 啥的环境，能大幅提高推理速度，有需要可以自己弄下（仅支持 cuda 显卡）
os.environ["RWKV_CUDA_ON"] = "0"

from rwkv.model import RWKV

from .pipeline import Pipeline, PipelineArgs
from .prompt import CHAT_FORMAT, INIT_PROMPT

cuda = torch.cuda.is_available()
DEFAULT_STRATEGY = "cuda fp16" if cuda else "cpu fp32"
DEFAULT_MODEL_DIR = Path("resource/chat/models")


class Chat:
    def __init__(self, strategy=DEFAULT_STRATEGY, model_dir=DEFAULT_MODEL_DIR) -> None:
        self.STRATEGY = strategy or DEFAULT_STRATEGY
        self.MODEL_DIR = model_dir
        self.MODEL_EXT = ".pth"
        self.MODEL_PATH = None
        self.TOKEN_PATH = self.MODEL_DIR / "rwkv_vocab_v20230424.txt"
        for f in self.MODEL_DIR.glob("*"):
            if f.suffix != self.MODEL_EXT:
                continue
            self.MODEL_PATH = f.with_suffix("")
            break
        if not self.MODEL_PATH:
            raise Exception(f"Chat model not found in {self.MODEL_DIR}")
        if not self.TOKEN_PATH.exists():
            raise Exception(f"Chat token not found in {self.TOKEN_PATH}")

        self.pipeline = None
        self.args = None
        self.all_state = defaultdict(lambda: None)
        self.all_occurrence = {}
        self.chat_locker = Lock()
        self.executor = ThreadPoolExecutor(max_workers=10)

        threading.Thread(target=self._load_model).start()

    def _load_model(self):
        model = RWKV(model=str(self.MODEL_PATH), strategy=self.STRATEGY)
        self.pipeline = Pipeline(model, str(self.TOKEN_PATH))
        self.args = PipelineArgs(
            temperature=1.0,
            top_p=0.7,
            alpha_frequency=0.25,
            alpha_presence=0.25,
            token_ban=[0],  # ban the generation of some tokens
            token_stop=[],  # stop generation whenever you see any token here
            ends=("\n"),
            ends_if_too_long=("。", "！", "？", "\n"),
        )

        INIT_STATE = deepcopy(self.pipeline.generate(INIT_PROMPT, token_count=200, args=self.args)[1])
        self.all_state = defaultdict(lambda: deepcopy(INIT_STATE))

    def chat(self, session: str, text: str, token_count: int = 50) -> str:
        while self.pipeline is None:
            time.sleep(0.1)
        future = self.executor.submit(self._chat, session, text, token_count)
        return future.result()

    def _chat(self, session: str, text: str, token_count: int = 50) -> str:
        with self.chat_locker:
            state = self.all_state[session]
            ctx = CHAT_FORMAT.format(text)
            occurrence = self.all_occurrence.get(session, {})

            out, state, occurrence = self.pipeline.generate(
                ctx, token_count=token_count, args=self.args, state=state, occurrence=occurrence
            )

            self.all_state[session] = deepcopy(state)
            self.all_occurrence[session] = occurrence
            return out.strip()

    def del_session(self, session: str):
        with self.chat_locker:
            if session in self.all_state:
                del self.all_state[session]
            if session in self.all_occurrence:
                del self.all_occurrence[session]


if __name__ == "__main__":
    chat = Chat("cpu fp32")
    while True:
        session = "main"
        text = input("text:")
        result = chat.chat(session, text)
        print(result)
