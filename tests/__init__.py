import os

os.environ["RWKV_JIT_ON"] = "1"
os.environ["RWKV_CUDA_ON"] = "0"  # if '1' then use CUDA kernel for seq mode (much faster)
from rwkv.model import RWKV  # pip install rwkv

model = RWKV(model="resource/caht/models/RWKV-x070-Pile-1.47B-20241210-ctx4096", strategy="cuda fp16")

out, state = model.forward([187, 510, 1563, 310, 247], None)  # use 20B_tokenizer.json
print(out.detach().cpu().numpy())  # get logits
out, state = model.forward([187, 510], None)
out, state = model.forward([1563], state)  # RNN has state (use deepcopy if you want to clone it)
out, state = model.forward([310, 247], state)
print(out.detach().cpu().numpy())  # same result as above
