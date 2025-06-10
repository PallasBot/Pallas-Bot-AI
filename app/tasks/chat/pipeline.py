########################################################################################################
# The RWKV Language Model - https://github.com/BlinkDL/RWKV-LM
########################################################################################################


import numpy as np
import torch
from torch.nn import functional

from .rwkv_tokenizer import TRIE_TOKENIZER


class PipelineArgs:
    def __init__(
        self,
        temperature=1.0,
        top_p=0.85,
        top_k=0,
        alpha_frequency=0.2,
        alpha_presence=0.2,
        alpha_decay=0.996,
        token_ban=[],
        token_stop=[],
        chunk_len=256,
        ends="\n\n",
        ends_if_too_long="。",
    ):
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.alpha_frequency = alpha_frequency  # Frequency Penalty (as in GPT-3)
        self.alpha_presence = alpha_presence  # Presence Penalty (as in GPT-3)
        self.alpha_decay = alpha_decay  # gradually decay the penalty
        self.token_ban = token_ban  # ban the generation of some tokens
        self.token_stop = token_stop  # stop generation whenever you see any token here
        self.chunk_len = chunk_len  # split input into chunks to save VRAM (shorter -> slower)
        self.ends = ends
        self.ends_if_too_long = ends_if_too_long


class Pipeline:
    def __init__(self, model, word_name):
        self.model = model
        self.tokenizer = TRIE_TOKENIZER(word_name)

    def refine_context(self, context):
        context = context.strip().split("\n")
        for c in range(len(context)):
            context[c] = context[c].strip().strip("\u3000").strip("\r")
        context = list(filter(lambda c: c != "", context))
        context = "\n" + ("\n".join(context)).strip()
        if not context:
            context = "\n"
        return context

    def encode(self, x):
        if "Tokenizer" in str(type(self.tokenizer)):
            return self.tokenizer.encode(x).ids
        else:
            return self.tokenizer.encode(x)

    def decode(self, x):
        return self.tokenizer.decode(x)

    def sample_logits(self, logits, temperature=1.0, top_p=0.85, top_k=0):
        if temperature == 0:
            temperature = 1.0
            top_p = 0
        probs = functional.softmax(logits.float(), dim=-1)
        top_k = int(top_k)
        # 'privateuseone' is the type of custom devices like `torch_directml.device()`
        if probs.device.type in ["cpu", "privateuseone"]:
            probs = probs.cpu().numpy()
            sorted_ids = np.argsort(probs)
            sorted_probs = probs[sorted_ids][::-1]
            cumulative_probs = np.cumsum(sorted_probs)
            cutoff = float(sorted_probs[np.argmax(cumulative_probs >= top_p)])
            probs[probs < cutoff] = 0
            if top_k < len(probs) and top_k > 0:
                probs[sorted_ids[:-top_k]] = 0
            if temperature != 1.0:
                probs **= 1.0 / temperature
            probs /= np.sum(probs)
            rng = np.random.default_rng()
            out = rng.choice(a=len(probs), p=probs)
            return int(out)
        else:
            sorted_ids = torch.argsort(probs)
            sorted_probs = probs[sorted_ids]
            sorted_probs = torch.flip(sorted_probs, dims=(0,))
            cumulative_probs = torch.cumsum(sorted_probs, dim=-1).cpu().numpy()
            cutoff = float(sorted_probs[np.argmax(cumulative_probs >= top_p)])
            probs[probs < cutoff] = 0
            if top_k < len(probs) and top_k > 0:
                probs[sorted_ids[:-top_k]] = 0
            if temperature != 1.0:
                probs **= 1.0 / temperature
            out = torch.multinomial(probs, num_samples=1)[0]
            return int(out)

    def generate(self, ctx, token_count=100, args=PipelineArgs(), callback=None, state=None, occurrence=None):
        all_tokens = []
        out_last = 0
        out_str = ""
        if occurrence is None:
            occurrence = {}
        for i in range(token_count):
            # forward & adjust prob.
            tokens = self.encode(ctx) if i == 0 else [token]
            while len(tokens) > 0:
                out, state = self.model.forward(tokens[: args.chunk_len], state)
                tokens = tokens[args.chunk_len :]

            for n in args.token_ban:
                out[n] = -float("inf")
            for n, occ in occurrence.items():
                out[n] -= args.alpha_presence + occ * args.alpha_frequency

            # sampler
            token = self.sample_logits(out, temperature=args.temperature, top_p=args.top_p, top_k=args.top_k)
            if token in args.token_stop:
                break
            all_tokens += [token]
            for xxx in occurrence:
                occurrence[xxx] *= args.alpha_decay

            ttt = self.decode([token])
            www = 1
            if ttt in " \t0123456789":
                www = 0
            # elif ttt in '\r\n,.;?!"\':+-*/=#@$%^&_`~|<>\\()[]{}，。；“”：？！（）【】':
            #     www = 0.5
            if token not in occurrence:
                occurrence[token] = www
            else:
                occurrence[token] += www
            # print(occurrence) # debug

            # output
            tmp = self.decode(all_tokens[out_last:])
            if "\ufffd" not in tmp:  # is valid utf-8 string?
                if callback:
                    callback(tmp)
                out_str += tmp
                out_last = i + 1
            if out_str.endswith(args.ends):
                break
            if i > token_count / 2 and out_str.endswith(args.ends_if_too_long):
                break
        return out_str, state, occurrence
