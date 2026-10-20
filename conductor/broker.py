import time
import hashlib
from conductor.models import Message, MsgStatus
from conductor.db import Store


class Broker:
    def __init__(self, store: Store, rate_limit_per_agent: int = 30, window_sec: float = 60.0):
        self.store = store
        self.rate_limit = rate_limit_per_agent
        self.window = window_sec
        self._rate: dict = {}  # agent -> list of timestamps
        self._seen_idempotency: set = set()
        self._message_log: list = []

    def _check_rate(self, sender: str) -> bool:
        now = time.time()
        ts = [t for t in self._rate.get(sender, []) if now - t < self.window]
        if len(ts) >= self.rate_limit:
            return False
        ts.append(now)
        self._rate[sender] = ts
        return True

    def _dedup_key(self, msg: Message) -> str:
        if msg.idempotency_key:
            return msg.idempotency_key
        h = hashlib.sha256()
        h.update((msg.sender + msg.recipient + msg.type + repr(msg.payload)).encode())
        return h.hexdigest()[:24]

    def _is_duplicate_content(self, msg: Message) -> bool:
        # collapse near-duplicate messages: same sender/recipient/type with same payload hash
        key = self._dedup_key(msg)
        for m in self._message_log[-50:]:
            if m.get("sender") == msg.sender and m.get("recipient") == msg.recipient and m.get("type") == msg.type:
                if m.get("key") == key:
                    return True
        return False

    def send(self, msg: Message, run_id: str, sender_token: str = None, agent_lookup=None) -> Message:
        # authenticate sender from token if provided
        if sender_token and agent_lookup:
            ag = agent_lookup(sender_token)
            if ag is None:
                raise PermissionError("unknown sender token")
            msg.sender = ag["agent_id"]
        # validate typed purpose
        if not msg.type:
            raise ValueError("message type required")
        if not self._check_rate(msg.sender):
            msg.status = MsgStatus.FAILED.value
            self.store.save_message(msg, run_id)
            raise RuntimeError("rate limit exceeded")
        if msg.idempotency_key in self._seen_idempotency:
            # already seen; return existing
            msgs = self.store.list_messages(run_id=run_id)
            for m in msgs:
                if m.get("idempotency_key") == msg.idempotency_key:
                    return Message(**{k: m[k] for k in Message.__dataclass_fields__ if k in m})
        if self._is_duplicate_content(msg):
            msg.status = MsgStatus.FAILED.value
            self.store.save_message(msg, run_id)
            raise ValueError("duplicate message collapsed")
        if not msg.idempotency_key:
            msg.idempotency_key = self._dedup_key(msg)
        self._seen_idempotency.add(msg.idempotency_key)
        # persist BEFORE delivery
        ok = self.store.save_message(msg, run_id)
        if not ok:
            # duplicate idempotency in db
            msgs = self.store.list_messages(run_id=run_id)
            for m in msgs:
                if m.get("idempotency_key") == msg.idempotency_key:
                    return Message(**{k: m[k] for k in Message.__dataclass_fields__ if k in m})
        self._message_log.append({"sender": msg.sender, "recipient": msg.recipient, "type": msg.type, "key": msg.idempotency_key})
        return msg

    def mark_delivered(self, message_id: str):
        self.store.update_message_status(message_id, MsgStatus.DELIVERED.value)

    def mark_acked(self, message_id: str):
        self.store.update_message_status(message_id, MsgStatus.ACKED.value)

    def inbox(self, recipient: str, run_id: str = None, status: str = None):
        return self.store.list_messages(run_id=run_id, recipient=recipient, status=status)