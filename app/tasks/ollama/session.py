from __future__ import annotations

import threading

_lock = threading.Lock()
_sessions: dict[str, list[dict[str, str]]] = {}


def get_messages(session: str, system_prompt: str) -> list[dict[str, str]]:
    with _lock:
        messages = _sessions.get(session)
        if messages is None:
            messages = [{"role": "system", "content": system_prompt}]
            _sessions[session] = messages
            return messages
        if messages and messages[0].get("role") == "system":
            if messages[0].get("content") != system_prompt:
                messages[0] = {"role": "system", "content": system_prompt}
        elif messages:
            messages.insert(0, {"role": "system", "content": system_prompt})
        else:
            messages.append({"role": "system", "content": system_prompt})
        return messages


def reset_session(session: str, system_prompt: str) -> None:
    with _lock:
        _sessions[session] = [{"role": "system", "content": system_prompt}]


def del_session(session: str) -> None:
    with _lock:
        _sessions.pop(session, None)


def message_count(session: str) -> int:
    with _lock:
        return len(_sessions.get(session, []))
