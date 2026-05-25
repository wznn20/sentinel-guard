from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Any, Callable


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _first_non_empty(*values: Any, default: str = "") -> str:
    for value in values:
        if value is None:
            continue
        text = _coerce_text(value).strip()
        if text:
            return text
    return default


def _get_nested(value: Any, *path: str, default: Any = None) -> Any:
    current = value
    for part in path:
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def _parse_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


@dataclass
class ChannelEvent:
    channel: str
    user: str
    text: str
    account: str = "default"
    peer: str = "*"
    thread_id: str = ""
    adapter: str = "generic"
    verified: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelAdapter:
    name: str
    channel: str
    description: str
    parser: Callable[[dict[str, Any]], ChannelEvent] | None = None

    def normalize(self, payload: dict[str, Any]) -> ChannelEvent:
        if self.parser:
            return self.parser(payload)
        return ChannelEvent(
            channel=self.channel,
            user=_first_non_empty(payload.get("user"), payload.get("author"), default="webhook-user"),
            text=_first_non_empty(payload.get("message"), payload.get("text")),
            account=_first_non_empty(payload.get("account"), default="default"),
            peer=_first_non_empty(payload.get("peer"), default="*"),
            thread_id=_first_non_empty(payload.get("thread_id")),
            adapter=self.name,
        )


class ChannelHub:
    DEFAULT_ADAPTERS = [
        "generic",
        "webhook",
        "discord",
        "slack",
        "telegram",
        "whatsapp",
        "signal",
        "mattermost",
        "matrix",
        "homeassistant",
        "email",
        "sms",
        "dingtalk",
        "api_server",
        "msgraph_webhook",
        "feishu",
        "wecom",
        "wecom_callback",
        "weixin",
        "bluebubbles",
        "qqbot",
        "yuanbao",
    ]

    _ADAPTER_SPECS = {
        "generic": ("webhook", "Generic webhook adapter", "_parse_generic"),
        "webhook": ("webhook", "Webhook adapter", "_parse_generic"),
        "discord": ("discord", "Discord adapter", "_parse_discord"),
        "slack": ("slack", "Slack adapter", "_parse_slack"),
        "telegram": ("telegram", "Telegram adapter", "_parse_telegram"),
        "whatsapp": ("whatsapp", "WhatsApp adapter", "_parse_whatsapp"),
        "signal": ("signal", "Signal adapter", "_parse_signal"),
        "mattermost": ("mattermost", "Mattermost adapter", "_parse_mattermost"),
        "matrix": ("matrix", "Matrix adapter", "_parse_matrix"),
        "homeassistant": ("homeassistant", "Home Assistant adapter", "_parse_homeassistant"),
        "email": ("email", "Email adapter", "_parse_email"),
        "sms": ("sms", "SMS adapter", "_parse_sms"),
        "dingtalk": ("dingtalk", "DingTalk adapter", "_parse_dingtalk"),
        "api_server": ("api_server", "API server adapter", "_parse_api_server"),
        "msgraph_webhook": ("msgraph_webhook", "Microsoft Graph webhook adapter", "_parse_msgraph_webhook"),
        "feishu": ("feishu", "Feishu adapter", "_parse_feishu"),
        "wecom": ("wecom", "WeCom adapter", "_parse_wecom"),
        "wecom_callback": ("wecom_callback", "WeCom callback adapter", "_parse_wecom_callback"),
        "weixin": ("weixin", "Weixin adapter", "_parse_weixin"),
        "bluebubbles": ("bluebubbles", "BlueBubbles adapter", "_parse_bluebubbles"),
        "qqbot": ("qqbot", "QQ Bot adapter", "_parse_qqbot"),
        "yuanbao": ("yuanbao", "Yuanbao adapter", "_parse_yuanbao"),
    }

    def __init__(
        self,
        stable_sessions: bool = True,
        adapters: list[str] | None = None,
        adapter_secrets: dict[str, str] | None = None,
    ):
        self.stable_sessions = stable_sessions
        names = adapters or list(self.DEFAULT_ADAPTERS)
        self.adapter_secrets = {str(key).lower(): str(value) for key, value in (adapter_secrets or {}).items()}
        self.adapters: dict[str, ChannelAdapter] = {}
        for name in names:
            normalized = str(name).strip().lower()
            if not normalized or normalized in self.adapters:
                continue
            self.adapters[normalized] = self._build_adapter(normalized)

    def _build_adapter(self, name: str) -> ChannelAdapter:
        channel, description, parser_name = self._ADAPTER_SPECS.get(
            name,
            ("webhook", f"{name} adapter", "_parse_generic"),
        )
        parser = getattr(self, parser_name)
        return ChannelAdapter(name=name, channel=channel, description=description, parser=parser)

    def _event(
        self,
        channel: str,
        payload: dict[str, Any],
        *,
        user: Any = None,
        text: Any = None,
        account: Any = None,
        peer: Any = None,
        thread_id: Any = None,
        adapter: str,
        default_user: str,
        default_peer: str,
        meta: dict[str, Any] | None = None,
    ) -> ChannelEvent:
        return ChannelEvent(
            channel=channel,
            user=_first_non_empty(user, payload.get("user"), default=default_user),
            text=_first_non_empty(text, payload.get("message"), payload.get("text")),
            account=_first_non_empty(account, payload.get("account"), default="default"),
            peer=_first_non_empty(peer, payload.get("peer"), default=default_peer),
            thread_id=_first_non_empty(thread_id, payload.get("thread_id")),
            adapter=adapter,
            meta=meta or {},
        )

    def session_id_for(self, event: ChannelEvent) -> str:
        if not self.stable_sessions:
            return ""
        base = "|".join(
            [
                event.channel,
                event.account,
                event.user,
                event.peer,
                event.thread_id or "-",
            ]
        )
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

    def normalize_webhook(self, payload: dict[str, Any]) -> ChannelEvent:
        adapter_name = str(payload.get("adapter", "generic")).strip().lower()
        return self.event_from(adapter_name, payload)

    def _parse_generic(self, payload: dict[str, Any]) -> ChannelEvent:
        return self._event(
            _first_non_empty(payload.get("channel"), default="webhook"),
            payload,
            user=payload.get("user") or payload.get("author"),
            text=payload.get("message") or payload.get("text") or payload.get("content"),
            account=payload.get("account"),
            peer=payload.get("peer"),
            thread_id=payload.get("thread_id"),
            adapter="generic",
            default_user="webhook-user",
            default_peer="*",
        )

    def _parse_discord(self, payload: dict[str, Any]) -> ChannelEvent:
        if "data" in payload and "type" in payload:
            member = payload.get("member") or {}
            user = member.get("user") or payload.get("user") or {}
            data = payload.get("data") or {}
            options = data.get("options") or []
            option_text = " ".join(
                _coerce_text(item.get("value"))
                for item in options
                if isinstance(item, dict) and item.get("value") is not None
            )
            return self._event(
                "discord",
                payload,
                user=user.get("username") or user.get("id"),
                text=data.get("custom_id") or data.get("name") or option_text,
                account=payload.get("guild_id"),
                peer=payload.get("channel_id"),
                thread_id=payload.get("id"),
                adapter="discord",
                default_user="discord-user",
                default_peer="discord",
                meta={
                    "guild_id": payload.get("guild_id"),
                    "channel_id": payload.get("channel_id"),
                    "interaction_id": payload.get("id"),
                    "interaction_token": payload.get("token"),
                    "application_id": payload.get("application_id"),
                },
            )
        author = payload.get("author") or {}
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        return self._event(
            "discord",
            payload,
            user=author.get("username") or author.get("id"),
            text=payload.get("content") or payload.get("message"),
            account=payload.get("guild_id"),
            peer=payload.get("channel_id") or payload.get("channel"),
            thread_id=payload.get("thread_id") or message.get("thread_id"),
            adapter="discord",
            default_user="discord-user",
            default_peer="discord",
            meta={
                "guild_id": payload.get("guild_id"),
                "channel_id": payload.get("channel_id") or payload.get("channel"),
                "message_id": payload.get("id") or message.get("id"),
            },
        )

    def _parse_slack(self, payload: dict[str, Any]) -> ChannelEvent:
        event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
        text = _first_non_empty(event.get("text"), payload.get("text"))
        if not text and event.get("type") == "app_mention":
            blocks = event.get("blocks") or []
            if isinstance(blocks, list) and blocks:
                text = json.dumps(blocks, ensure_ascii=False)
        return self._event(
            "slack",
            payload,
            user=event.get("user"),
            text=text,
            account=payload.get("team_id"),
            peer=event.get("channel"),
            thread_id=event.get("thread_ts"),
            adapter="slack",
            default_user="slack-user",
            default_peer="slack",
            meta={
                "channel": event.get("channel"),
                "thread_ts": event.get("thread_ts"),
                "ts": event.get("ts"),
                "team_id": payload.get("team_id"),
            },
        )

    def _parse_telegram(self, payload: dict[str, Any]) -> ChannelEvent:
        if "callback_query" in payload:
            callback = payload.get("callback_query") or {}
            sender = callback.get("from") or {}
            message = callback.get("message") or {}
            chat = message.get("chat") or {}
            return self._event(
                "telegram",
                payload,
                user=sender.get("username") or sender.get("id"),
                text=callback.get("data"),
                account=payload.get("bot_id"),
                peer=chat.get("id"),
                thread_id=callback.get("id"),
                adapter="telegram",
                default_user="telegram-user",
                default_peer="*",
                meta={
                    "chat_id": chat.get("id"),
                    "callback_query_id": callback.get("id"),
                    "message_id": message.get("message_id"),
                },
            )
        message = payload.get("message") or payload.get("edited_message") or payload.get("channel_post") or payload
        sender = message.get("from") if isinstance(message, dict) else {}
        chat = message.get("chat") if isinstance(message, dict) else {}
        return self._event(
            "telegram",
            payload,
            user=_get_nested(message, "from", "username") or _get_nested(message, "from", "id"),
            text=_get_nested(message, "text") or _get_nested(message, "caption"),
            account=payload.get("bot_id"),
            peer=chat.get("id"),
            thread_id=message.get("message_thread_id") if isinstance(message, dict) else None,
            adapter="telegram",
            default_user="telegram-user",
            default_peer="*",
            meta={
                "chat_id": chat.get("id"),
                "message_id": message.get("message_id") if isinstance(message, dict) else None,
                "message_thread_id": message.get("message_thread_id") if isinstance(message, dict) else None,
            },
        )

    def _parse_whatsapp(self, payload: dict[str, Any]) -> ChannelEvent:
        entries = payload.get("entry") or []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                for change in entry.get("changes") or []:
                    if not isinstance(change, dict):
                        continue
                    value = change.get("value") or {}
                    messages = value.get("messages") or []
                    contacts = value.get("contacts") or []
                    if not isinstance(messages, list) or not messages:
                        continue
                    message = messages[0] if isinstance(messages[0], dict) else {}
                    profile = contacts[0].get("profile") if contacts and isinstance(contacts[0], dict) else {}
                    interactive = message.get("interactive") or {}
                    return self._event(
                        "whatsapp",
                        payload,
                        user=_get_nested(profile, "name") or message.get("from"),
                        text=(
                            _get_nested(message, "text", "body")
                            or _get_nested(message, "button", "text")
                            or _get_nested(interactive, "button_reply", "title")
                            or _get_nested(interactive, "list_reply", "title")
                        ),
                        account=_get_nested(value, "metadata", "phone_number_id") or value.get("phone_number_id"),
                        peer=message.get("from"),
                        thread_id=message.get("id"),
                        adapter="whatsapp",
                        default_user="whatsapp-user",
                        default_peer="*",
                        meta={
                            "from": message.get("from"),
                            "message_id": message.get("id"),
                            "phone_number_id": _get_nested(value, "metadata", "phone_number_id") or value.get("phone_number_id"),
                        },
                    )
        return self._event(
            "whatsapp",
            payload,
            user=payload.get("from_name"),
            text=payload.get("body") or payload.get("message"),
            account=payload.get("phone_number_id"),
            peer=payload.get("from"),
            thread_id=payload.get("thread_id"),
            adapter="whatsapp",
            default_user="whatsapp-user",
            default_peer="*",
            meta={
                "from": payload.get("from"),
                "phone_number_id": payload.get("phone_number_id"),
            },
        )

    def _parse_signal(self, payload: dict[str, Any]) -> ChannelEvent:
        envelope = payload.get("envelope") or _get_nested(payload, "data", "envelope") or {}
        data_message = envelope.get("dataMessage") or payload.get("dataMessage") or {}
        group_info = data_message.get("groupInfo") or {}
        return self._event(
            "signal",
            payload,
            user=envelope.get("sourceName") or envelope.get("sourceNumber") or envelope.get("sourceUuid"),
            text=data_message.get("message") or payload.get("message"),
            account=envelope.get("account") or payload.get("account"),
            peer=group_info.get("groupId") or envelope.get("sourceNumber") or envelope.get("sourceUuid"),
            thread_id=envelope.get("timestamp") or payload.get("thread_id"),
            adapter="signal",
            default_user="signal-user",
            default_peer="signal",
            meta={
                "source_number": envelope.get("sourceNumber"),
                "source_uuid": envelope.get("sourceUuid"),
                "timestamp": envelope.get("timestamp"),
                "group_id": group_info.get("groupId"),
            },
        )

    def _parse_mattermost(self, payload: dict[str, Any]) -> ChannelEvent:
        post = payload.get("post")
        parsed_post = _parse_json_object(post) if not isinstance(post, dict) else post
        return self._event(
            "mattermost",
            payload,
            user=payload.get("user_name") or payload.get("username") or payload.get("user_id"),
            text=(parsed_post or {}).get("message") if isinstance(parsed_post, dict) else payload.get("text"),
            account=payload.get("team_id"),
            peer=payload.get("channel_id") or (parsed_post or {}).get("channel_id"),
            thread_id=(parsed_post or {}).get("root_id") or (parsed_post or {}).get("id") or payload.get("trigger_id"),
            adapter="mattermost",
            default_user="mattermost-user",
            default_peer="mattermost",
            meta={
                "team_id": payload.get("team_id"),
                "channel_id": payload.get("channel_id") or (parsed_post or {}).get("channel_id"),
                "post_id": (parsed_post or {}).get("id"),
                "response_url": payload.get("response_url"),
            },
        )

    def _parse_matrix(self, payload: dict[str, Any]) -> ChannelEvent:
        content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
        relates = content.get("m.relates_to") if isinstance(content.get("m.relates_to"), dict) else {}
        return self._event(
            "matrix",
            payload,
            user=payload.get("sender"),
            text=content.get("body") or content.get("formatted_body") or payload.get("text"),
            account=payload.get("homeserver") or payload.get("account"),
            peer=payload.get("room_id"),
            thread_id=relates.get("event_id") or payload.get("event_id"),
            adapter="matrix",
            default_user="matrix-user",
            default_peer="matrix",
            meta={
                "room_id": payload.get("room_id"),
                "event_id": payload.get("event_id"),
                "relates_to": relates,
            },
        )

    def _parse_homeassistant(self, payload: dict[str, Any]) -> ChannelEvent:
        event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        return self._event(
            "homeassistant",
            payload,
            user=data.get("user_id") or payload.get("user_id"),
            text=data.get("text") or data.get("message") or payload.get("text"),
            account=payload.get("config_entry_id") or payload.get("account"),
            peer=data.get("conversation_id") or payload.get("conversation_id"),
            thread_id=data.get("thread_id") or payload.get("thread_id"),
            adapter="homeassistant",
            default_user="homeassistant",
            default_peer="homeassistant",
            meta={
                "conversation_id": data.get("conversation_id") or payload.get("conversation_id"),
                "event_type": event.get("event_type"),
            },
        )

    def _parse_email(self, payload: dict[str, Any]) -> ChannelEvent:
        headers = payload.get("headers") if isinstance(payload.get("headers"), dict) else {}
        subject = payload.get("subject") or headers.get("subject")
        body = payload.get("text") or payload.get("body") or payload.get("message")
        text = body or subject or ""
        if subject and body:
            text = f"Subject: {subject}\n\n{body}"
        return self._event(
            "email",
            payload,
            user=payload.get("from") or headers.get("from") or payload.get("sender"),
            text=text,
            account=payload.get("to") or headers.get("to") or payload.get("account"),
            peer=payload.get("from") or headers.get("from"),
            thread_id=payload.get("message_id") or headers.get("message-id"),
            adapter="email",
            default_user="email-user",
            default_peer="email",
            meta={
                "from": payload.get("from") or headers.get("from"),
                "to": payload.get("to") or headers.get("to"),
                "subject": subject,
                "message_id": payload.get("message_id") or headers.get("message-id"),
            },
        )

    def _parse_sms(self, payload: dict[str, Any]) -> ChannelEvent:
        return self._event(
            "sms",
            payload,
            user=payload.get("From") or payload.get("from"),
            text=payload.get("Body") or payload.get("body") or payload.get("message"),
            account=payload.get("AccountSid") or payload.get("account") or payload.get("To"),
            peer=payload.get("From") or payload.get("from"),
            thread_id=payload.get("MessageSid") or payload.get("SmsSid") or payload.get("thread_id"),
            adapter="sms",
            default_user="sms-user",
            default_peer="sms",
            meta={
                "from": payload.get("From") or payload.get("from"),
                "to": payload.get("To") or payload.get("to"),
                "message_sid": payload.get("MessageSid") or payload.get("SmsSid"),
            },
        )

    def _parse_dingtalk(self, payload: dict[str, Any]) -> ChannelEvent:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        text_block = data.get("text") if isinstance(data.get("text"), dict) else {}
        return self._event(
            "dingtalk",
            payload,
            user=data.get("senderNick") or data.get("senderStaffId") or data.get("senderId"),
            text=text_block.get("content") or data.get("content") or payload.get("text"),
            account=data.get("chatbotCorpId") or payload.get("account"),
            peer=data.get("conversationId") or data.get("sessionWebhook"),
            thread_id=data.get("msgId") or data.get("conversationId"),
            adapter="dingtalk",
            default_user="dingtalk-user",
            default_peer="dingtalk",
            meta={
                "conversation_id": data.get("conversationId"),
                "msg_id": data.get("msgId"),
                "session_webhook": data.get("sessionWebhook"),
            },
        )

    def _parse_api_server(self, payload: dict[str, Any]) -> ChannelEvent:
        return self._event(
            "api_server",
            payload,
            user=payload.get("user"),
            text=payload.get("message") or payload.get("text"),
            account=payload.get("account"),
            peer=payload.get("peer"),
            thread_id=payload.get("request_id") or payload.get("thread_id"),
            adapter="api_server",
            default_user="api-user",
            default_peer="api",
            meta={
                "request_id": payload.get("request_id"),
            },
        )

    def _parse_msgraph_webhook(self, payload: dict[str, Any]) -> ChannelEvent:
        notifications = payload.get("value") if isinstance(payload.get("value"), list) else []
        notification = notifications[0] if notifications and isinstance(notifications[0], dict) else {}
        summary = _first_non_empty(
            payload.get("text"),
            notification.get("summary"),
            f"{_first_non_empty(notification.get('changeType'), default='change')} {_first_non_empty(notification.get('resource'))}".strip(),
        )
        return self._event(
            "msgraph_webhook",
            payload,
            user=notification.get("creatorId") or notification.get("tenantId"),
            text=summary,
            account=notification.get("subscriptionId") or payload.get("account"),
            peer=notification.get("resource") or payload.get("peer"),
            thread_id=notification.get("id") or notification.get("clientState"),
            adapter="msgraph_webhook",
            default_user="msgraph",
            default_peer="msgraph",
            meta={
                "notification": notification,
                "subscription_id": notification.get("subscriptionId"),
            },
        )

    def _parse_feishu(self, payload: dict[str, Any]) -> ChannelEvent:
        event = payload.get("event") if isinstance(payload.get("event"), dict) else payload.get("data") or {}
        sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
        sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        content_obj = _parse_json_object(message.get("content"))
        return self._event(
            "feishu",
            payload,
            user=sender_id.get("union_id") or sender_id.get("open_id") or sender_id.get("user_id"),
            text=(
                _get_nested(content_obj, "text")
                or _get_nested(content_obj, "title")
                or message.get("content")
                or payload.get("text")
            ),
            account=payload.get("app_id") or payload.get("tenant_key") or payload.get("account"),
            peer=message.get("chat_id") or event.get("open_chat_id") or payload.get("peer"),
            thread_id=message.get("message_id") or event.get("open_message_id") or payload.get("thread_id"),
            adapter="feishu",
            default_user="feishu-user",
            default_peer="feishu",
            meta={
                "chat_id": message.get("chat_id") or event.get("open_chat_id"),
                "message_id": message.get("message_id") or event.get("open_message_id"),
                "tenant_key": payload.get("tenant_key"),
            },
        )

    def _parse_wecom(self, payload: dict[str, Any]) -> ChannelEvent:
        text_block = payload.get("text") if isinstance(payload.get("text"), dict) else {}
        sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
        return self._event(
            "wecom",
            payload,
            user=sender.get("userid") or payload.get("from") or payload.get("userid"),
            text=text_block.get("content") or payload.get("content") or payload.get("message"),
            account=payload.get("corp_id") or payload.get("agent_id") or payload.get("account"),
            peer=payload.get("conversation_id") or payload.get("chat_id"),
            thread_id=payload.get("msgid") or payload.get("thread_id"),
            adapter="wecom",
            default_user="wecom-user",
            default_peer="wecom",
            meta={
                "conversation_id": payload.get("conversation_id") or payload.get("chat_id"),
                "msgid": payload.get("msgid"),
            },
        )

    def _parse_wecom_callback(self, payload: dict[str, Any]) -> ChannelEvent:
        xml = payload.get("xml") if isinstance(payload.get("xml"), dict) else payload
        return self._event(
            "wecom_callback",
            payload,
            user=xml.get("FromUserName") or payload.get("user"),
            text=xml.get("Content") or payload.get("content") or payload.get("message"),
            account=xml.get("AgentID") or payload.get("account"),
            peer=xml.get("ConversationId") or xml.get("FromUserName") or payload.get("peer"),
            thread_id=xml.get("MsgId") or payload.get("thread_id"),
            adapter="wecom_callback",
            default_user="wecom-user",
            default_peer="wecom",
            meta={
                "from_user_name": xml.get("FromUserName"),
                "agent_id": xml.get("AgentID"),
                "msg_id": xml.get("MsgId"),
            },
        )

    def _parse_weixin(self, payload: dict[str, Any]) -> ChannelEvent:
        msg_items = payload.get("msg_items") if isinstance(payload.get("msg_items"), list) else []
        first_item = msg_items[0] if msg_items and isinstance(msg_items[0], dict) else {}
        text_block = payload.get("text") if isinstance(payload.get("text"), dict) else {}
        return self._event(
            "weixin",
            payload,
            user=payload.get("from") or payload.get("sender") or payload.get("wxid"),
            text=first_item.get("content") or text_block.get("content") or payload.get("content") or payload.get("text"),
            account=payload.get("account_id") or payload.get("account"),
            peer=payload.get("conversation_id") or payload.get("chat_id") or payload.get("from"),
            thread_id=payload.get("msg_id") or payload.get("thread_id"),
            adapter="weixin",
            default_user="weixin-user",
            default_peer="weixin",
            meta={
                "conversation_id": payload.get("conversation_id") or payload.get("chat_id"),
                "msg_id": payload.get("msg_id"),
                "account_id": payload.get("account_id"),
            },
        )

    def _parse_bluebubbles(self, payload: dict[str, Any]) -> ChannelEvent:
        handle = payload.get("handle") if isinstance(payload.get("handle"), dict) else {}
        return self._event(
            "bluebubbles",
            payload,
            user=handle.get("address") or payload.get("from") or payload.get("sender"),
            text=payload.get("text") or payload.get("message"),
            account=payload.get("service") or payload.get("account"),
            peer=payload.get("chatGuid") or payload.get("chat_guid") or payload.get("peer"),
            thread_id=payload.get("guid") or payload.get("thread_id"),
            adapter="bluebubbles",
            default_user="bluebubbles-user",
            default_peer="bluebubbles",
            meta={
                "chat_guid": payload.get("chatGuid") or payload.get("chat_guid"),
                "guid": payload.get("guid"),
            },
        )

    def _parse_qqbot(self, payload: dict[str, Any]) -> ChannelEvent:
        data = payload.get("d") if isinstance(payload.get("d"), dict) else payload.get("data") or payload
        author = data.get("author") if isinstance(data.get("author"), dict) else {}
        member = data.get("member") if isinstance(data.get("member"), dict) else {}
        interaction = data.get("data") if isinstance(data.get("data"), dict) else {}
        resolved = interaction.get("resolved") if isinstance(interaction.get("resolved"), dict) else {}
        return self._event(
            "qqbot",
            payload,
            user=author.get("username") or author.get("member_openid") or member.get("user_id") or data.get("user_openid"),
            text=(
                data.get("content")
                or interaction.get("button_data")
                or resolved.get("button_data")
                or interaction.get("name")
                or payload.get("text")
            ),
            account=data.get("guild_id") or data.get("appid") or payload.get("account"),
            peer=data.get("channel_id") or data.get("group_openid") or data.get("direct_message_guild_id"),
            thread_id=data.get("id") or data.get("msg_id") or payload.get("thread_id"),
            adapter="qqbot",
            default_user="qqbot-user",
            default_peer="qqbot",
            meta={
                "channel_id": data.get("channel_id"),
                "guild_id": data.get("guild_id"),
                "msg_id": data.get("id") or data.get("msg_id"),
                "group_openid": data.get("group_openid"),
            },
        )

    def _parse_yuanbao(self, payload: dict[str, Any]) -> ChannelEvent:
        message = payload.get("message") if isinstance(payload.get("message"), dict) else payload
        sender = message.get("sender") if isinstance(message.get("sender"), dict) else {}
        return self._event(
            "yuanbao",
            payload,
            user=sender.get("nickname") or sender.get("uid") or payload.get("from_uin"),
            text=message.get("content") or message.get("text") or payload.get("text"),
            account=payload.get("bot_appid") or payload.get("account"),
            peer=payload.get("group_code") or payload.get("conversation_id") or payload.get("to_account"),
            thread_id=payload.get("msg_id") or payload.get("msg_seq") or payload.get("thread_id"),
            adapter="yuanbao",
            default_user="yuanbao-user",
            default_peer="yuanbao",
            meta={
                "group_code": payload.get("group_code"),
                "to_account": payload.get("to_account"),
                "msg_id": payload.get("msg_id"),
            },
        )

    def list_adapters(self) -> list[dict[str, str]]:
        return [
            {
                "name": adapter.name,
                "channel": adapter.channel,
                "description": adapter.description,
            }
            for adapter in self.adapters.values()
        ]

    def event_from(self, adapter_name: str, payload: dict[str, Any]) -> ChannelEvent:
        normalized = str(adapter_name or "generic").strip().lower()
        adapter = self.adapters.get(normalized, self.adapters.get("generic"))
        if not adapter:
            return self._parse_generic(payload)
        event = adapter.normalize(payload)
        event.adapter = adapter.name
        event.verified = self.verify(adapter.name, payload)
        return event

    def verify(self, adapter_name: str, payload: dict[str, Any]) -> bool:
        normalized = str(adapter_name or "generic").strip().lower()
        secret = self.adapter_secrets.get(normalized, "")
        if not secret:
            return False
        headers = {str(k).lower(): str(v) for k, v in (payload.get("headers") or {}).items()}
        raw_body = str(payload.get("raw_body", ""))

        if normalized == "slack":
            return self._verify_slack(secret, headers, raw_body)
        if normalized == "telegram":
            return self._verify_telegram(secret, headers)
        if normalized == "discord":
            return self._verify_discord(secret, headers, raw_body)
        if normalized == "feishu":
            return self._verify_feishu(secret, payload)
        if normalized == "whatsapp":
            return self._verify_whatsapp(secret, payload)
        return self._verify_generic(secret, payload)

    def protocol_response(self, adapter_name: str, payload: dict[str, Any]) -> dict[str, Any] | str | None:
        normalized = str(adapter_name or "generic").strip().lower()
        if normalized == "slack" and payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}
        if normalized == "slack" and payload.get("type") == "event_callback":
            return {"ok": True, "retry_after": _get_nested(payload, "headers", "x-slack-retry-num")}
        if normalized == "discord" and int(payload.get("type", 0) or 0) == 1:
            return {"type": 1}
        if normalized == "discord" and int(payload.get("type", 0) or 0) == 2:
            return {"type": 5}
        if normalized == "telegram" and "callback_query" in payload:
            callback = payload.get("callback_query") or {}
            return {
                "method": "answerCallbackQuery",
                "callback_query_id": callback.get("id", ""),
                "text": "Received",
            }
        if normalized == "telegram" and any(key in payload for key in ["edited_message", "channel_post", "message"]):
            return {"ok": True}
        if normalized == "feishu" and payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}
        if normalized == "msgraph_webhook":
            token = payload.get("validationToken") or _get_nested(payload, "query", "validationToken")
            if token:
                return str(token)
        if normalized == "wecom_callback":
            echostr = payload.get("echostr") or _get_nested(payload, "query", "echostr")
            if echostr:
                return str(echostr)
        if normalized == "whatsapp":
            challenge = payload.get("hub.challenge") or _get_nested(payload, "query", "hub.challenge")
            if challenge:
                return str(challenge)
        return None

    def requires_verification(self, adapter_name: str) -> bool:
        normalized = str(adapter_name or "generic").strip().lower()
        return bool(self.adapter_secrets.get(normalized, ""))

    def _verify_generic(self, secret: str, payload: dict[str, Any]) -> bool:
        signature = str(payload.get("signature", ""))
        if not signature:
            return False
        canonical = _first_non_empty(payload.get("message"), payload.get("text"), payload.get("content"))
        digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, digest)

    def _verify_slack(self, secret: str, headers: dict[str, str], raw_body: str) -> bool:
        signature = headers.get("x-slack-signature", "")
        timestamp = headers.get("x-slack-request-timestamp", "")
        if not signature or not timestamp:
            return False
        body = raw_body or "{}"
        basestring = f"v0:{timestamp}:{body}"
        digest = "v0=" + hmac.new(secret.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, digest)

    def _verify_telegram(self, secret: str, headers: dict[str, str]) -> bool:
        token = headers.get("x-telegram-bot-api-secret-token", "")
        return bool(token) and hmac.compare_digest(token, secret)

    def _verify_discord(self, public_key: str, headers: dict[str, str], raw_body: str) -> bool:
        signature = headers.get("x-signature-ed25519", "")
        timestamp = headers.get("x-signature-timestamp", "")
        if not signature or not timestamp or not raw_body:
            return False
        try:
            from nacl.signing import VerifyKey
        except Exception:
            return False
        try:
            verify_key = VerifyKey(bytes.fromhex(public_key))
            verify_key.verify(f"{timestamp}{raw_body}".encode("utf-8"), bytes.fromhex(signature))
            return True
        except Exception:
            return False

    def _verify_feishu(self, secret: str, payload: dict[str, Any]) -> bool:
        token = payload.get("token") or _get_nested(payload, "header", "token")
        token_text = _coerce_text(token).strip()
        return bool(token_text) and hmac.compare_digest(token_text, secret)

    def _verify_whatsapp(self, secret: str, payload: dict[str, Any]) -> bool:
        token = payload.get("hub.verify_token") or _get_nested(payload, "query", "hub.verify_token")
        token_text = _coerce_text(token).strip()
        return bool(token_text) and hmac.compare_digest(token_text, secret)
