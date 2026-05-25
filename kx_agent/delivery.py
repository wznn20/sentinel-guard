from __future__ import annotations

import base64
import email.message
import json
import smtplib
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any

from .channels import ChannelEvent


@dataclass
class DeliveryPlan:
    platform: str
    mode: str
    target: str
    body: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)
    method: str = "POST"
    url: str = ""
    note: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeliveryResult:
    success: bool
    platform: str
    mode: str
    target: str
    url: str = ""
    status_code: int | None = None
    response_text: str = ""
    response_json: dict[str, Any] | None = None
    error: str = ""
    request_body: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False


class DeliveryService:
    """Plan and execute outbound replies for platform events."""

    def __init__(self, config):
        self.config = config

    def build_reply_plan(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        platform = (event.adapter or event.channel or "generic").lower()
        builder = getattr(self, f"_plan_{platform}", self._plan_generic)
        return builder(event, reply_text)

    def send_reply(self, event: ChannelEvent, reply_text: str) -> tuple[DeliveryPlan, DeliveryResult]:
        plan = self.build_reply_plan(event, reply_text)
        if not self.config.delivery.auto_send:
            return plan, self._dry_run(plan, "auto_send disabled")
        return plan, self.execute(plan)

    def execute(self, plan: DeliveryPlan) -> DeliveryResult:
        if not self.config.delivery.enabled:
            return DeliveryResult(
                success=False,
                platform=plan.platform,
                mode=plan.mode,
                target=plan.target,
                url=plan.url,
                error="delivery disabled",
                request_body=plan.body,
            )
        handler = getattr(self, f"_send_{plan.platform}", self._send_http_webhook)
        try:
            return handler(plan)
        except Exception as exc:  # pragma: no cover - defensive
            return DeliveryResult(
                success=False,
                platform=plan.platform,
                mode=plan.mode,
                target=plan.target,
                url=plan.url,
                error=str(exc),
                request_body=plan.body,
            )

    def _dry_run(self, plan: DeliveryPlan, reason: str) -> DeliveryResult:
        return DeliveryResult(
            success=True,
            platform=plan.platform,
            mode=plan.mode,
            target=plan.target,
            url=plan.url,
            response_text=reason,
            request_body=plan.body,
            dry_run=True,
        )

    def _plan_generic(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform=event.adapter or event.channel,
            mode="echo",
            target=event.peer,
            body={
                "channel": event.channel,
                "user": event.user,
                "peer": event.peer,
                "thread_id": event.thread_id,
                "reply": reply_text,
            },
            note="Generic webhook echo payload.",
            meta=event.meta,
        )

    def _plan_slack(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="slack",
            mode="api",
            target=event.meta.get("channel") or event.peer,
            body={
                "channel": event.meta.get("channel") or event.peer,
                "text": reply_text,
                "thread_ts": event.meta.get("thread_ts") or event.thread_id or None,
            },
            note="Slack chat.postMessage payload.",
            meta=event.meta,
        )

    def _plan_discord(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        interaction_token = event.meta.get("interaction_token")
        if interaction_token:
            return DeliveryPlan(
                platform="discord",
                mode="interaction",
                target=event.meta.get("interaction_id") or event.thread_id,
                body={"type": 4, "data": {"content": reply_text}},
                note="Discord interaction callback payload.",
                meta=event.meta,
            )
        return DeliveryPlan(
            platform="discord",
            mode="webhook",
            target=event.meta.get("channel_id") or event.peer,
            body={"content": reply_text},
            note="Discord webhook/channel message payload.",
            meta=event.meta,
        )

    def _plan_telegram(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        body: dict[str, Any] = {
            "chat_id": event.meta.get("chat_id") or event.peer,
            "text": reply_text,
        }
        if event.meta.get("message_thread_id"):
            body["message_thread_id"] = event.meta["message_thread_id"]
        if event.meta.get("message_id"):
            body["reply_to_message_id"] = event.meta["message_id"]
        return DeliveryPlan(
            platform="telegram",
            mode="bot_api",
            target=str(body["chat_id"]),
            body=body,
            note="Telegram sendMessage payload.",
            meta=event.meta,
        )

    def _plan_whatsapp(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="whatsapp",
            mode="graph_api",
            target=event.meta.get("from") or event.peer,
            body={
                "messaging_product": "whatsapp",
                "to": event.meta.get("from") or event.peer,
                "phone_number_id": event.meta.get("phone_number_id"),
                "type": "text",
                "text": {"body": reply_text},
            },
            note="WhatsApp Cloud API text payload.",
            meta=event.meta,
        )

    def _plan_signal(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="signal",
            mode="json_rpc",
            target=event.meta.get("group_id") or event.meta.get("source_number") or event.peer,
            body={
                "recipient": event.meta.get("source_number"),
                "group_id": event.meta.get("group_id"),
                "message": reply_text,
            },
            note="Signal send plan for signal-cli JSON-RPC.",
            meta=event.meta,
        )

    def _plan_mattermost(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        response_url = event.meta.get("response_url")
        if response_url:
            return DeliveryPlan(
                platform="mattermost",
                mode="response_url",
                target=response_url,
                body={"text": reply_text},
                url=response_url,
                note="Mattermost slash/action response payload.",
                meta=event.meta,
            )
        return DeliveryPlan(
            platform="mattermost",
            mode="api",
            target=event.meta.get("channel_id") or event.peer,
            body={"channel_id": event.meta.get("channel_id") or event.peer, "message": reply_text},
            note="Mattermost create-post payload.",
            meta=event.meta,
        )

    def _plan_matrix(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="matrix",
            mode="client_api",
            target=event.meta.get("room_id") or event.peer,
            body={
                "msgtype": "m.text",
                "body": reply_text,
                "m.relates_to": {"m.in_reply_to": {"event_id": event.meta.get("event_id")}} if event.meta.get("event_id") else None,
            },
            note="Matrix room message payload.",
            meta=event.meta,
        )

    def _plan_homeassistant(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="homeassistant",
            mode="conversation",
            target=event.meta.get("conversation_id") or event.peer,
            body={
                "conversation_id": event.meta.get("conversation_id") or event.peer,
                "response": reply_text,
            },
            note="Home Assistant conversation response payload.",
            meta=event.meta,
        )

    def _plan_email(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        subject = event.meta.get("subject") or "KX Agent reply"
        return DeliveryPlan(
            platform="email",
            mode="smtp",
            target=event.meta.get("from") or event.user,
            body={
                "to": event.meta.get("from") or event.user,
                "subject": f"Re: {subject}",
                "text": reply_text,
                "in_reply_to": event.meta.get("message_id"),
            },
            note="Email reply plan.",
            meta=event.meta,
        )

    def _plan_sms(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="sms",
            mode="twilio",
            target=event.meta.get("from") or event.user,
            body={"to": event.meta.get("from") or event.user, "body": reply_text},
            note="Twilio SMS payload.",
            meta=event.meta,
        )

    def _plan_dingtalk(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        webhook = event.meta.get("session_webhook") or event.peer
        return DeliveryPlan(
            platform="dingtalk",
            mode="webhook",
            target=webhook,
            body={"msgtype": "text", "text": {"content": reply_text}},
            url=webhook,
            note="DingTalk webhook payload.",
            meta=event.meta,
        )

    def _plan_api_server(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="api_server",
            mode="api",
            target=event.meta.get("request_id") or event.thread_id,
            body={"reply": reply_text},
            note="API server reply envelope.",
            meta=event.meta,
        )

    def _plan_msgraph_webhook(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="msgraph_webhook",
            mode="notification_only",
            target=event.meta.get("subscription_id") or event.peer,
            body={"reply": reply_text},
            note="Microsoft Graph webhooks are inbound-only; this is an internal handoff plan.",
            meta=event.meta,
        )

    def _plan_feishu(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="feishu",
            mode="webhook",
            target=event.meta.get("chat_id") or event.peer,
            body={"msg_type": "text", "content": {"text": reply_text}},
            note="Feishu IM webhook-style payload.",
            meta=event.meta,
        )

    def _plan_wecom(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="wecom",
            mode="webhook",
            target=event.meta.get("conversation_id") or event.peer,
            body={"msgtype": "markdown", "markdown": {"content": reply_text}},
            note="WeCom conversation reply payload.",
            meta=event.meta,
        )

    def _plan_wecom_callback(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="wecom_callback",
            mode="webhook",
            target=event.meta.get("from_user_name") or event.user,
            body={"msgtype": "text", "text": {"content": reply_text}},
            note="WeCom callback reply payload.",
            meta=event.meta,
        )

    def _plan_weixin(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="weixin",
            mode="webhook",
            target=event.meta.get("conversation_id") or event.peer,
            body={"content": reply_text},
            note="Weixin reply payload.",
            meta=event.meta,
        )

    def _plan_bluebubbles(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="bluebubbles",
            mode="webhook",
            target=event.meta.get("chat_guid") or event.peer,
            body={"chatGuid": event.meta.get("chat_guid") or event.peer, "message": reply_text},
            note="BlueBubbles server send payload.",
            meta=event.meta,
        )

    def _plan_qqbot(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="qqbot",
            mode="webhook",
            target=event.meta.get("channel_id") or event.meta.get("group_openid") or event.peer,
            body={"content": reply_text, "msg_id": event.meta.get("msg_id")},
            note="QQ Bot reply payload.",
            meta=event.meta,
        )

    def _plan_yuanbao(self, event: ChannelEvent, reply_text: str) -> DeliveryPlan:
        return DeliveryPlan(
            platform="yuanbao",
            mode="webhook",
            target=event.meta.get("group_code") or event.meta.get("to_account") or event.peer,
            body={
                "group_code": event.meta.get("group_code"),
                "to_account": event.meta.get("to_account"),
                "content": reply_text,
            },
            note="Yuanbao gateway send payload.",
            meta=event.meta,
        )

    def _send_http_webhook(self, plan: DeliveryPlan) -> DeliveryResult:
        url = plan.url or self.config.delivery.platform_base_urls.get(plan.platform, "")
        if not url:
            if plan.mode in {"notification_only", "echo", "api"}:
                return self._dry_run(plan, f"{plan.platform} is outbound-less without an explicit URL")
            return DeliveryResult(
                success=False,
                platform=plan.platform,
                mode=plan.mode,
                target=plan.target,
                error=f"no webhook/url configured for {plan.platform}",
                request_body=plan.body,
            )
        return self._post_json(
            url,
            plan.body,
            headers=plan.headers,
            platform=plan.platform,
            mode=plan.mode,
            target=plan.target,
        )

    def _send_slack(self, plan: DeliveryPlan) -> DeliveryResult:
        webhook_url = self.config.delivery.platform_base_urls.get("slack", "")
        token = self.config.delivery.platform_tokens.get("slack", "")
        if webhook_url:
            return self._post_json(webhook_url, plan.body, headers=plan.headers, platform="slack", mode=plan.mode, target=plan.target)
        if not token:
            return DeliveryResult(success=False, platform="slack", mode=plan.mode, target=plan.target, error="slack token or webhook url missing", request_body=plan.body)
        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        return self._post_json(url, plan.body, headers=headers, platform="slack", mode=plan.mode, target=plan.target)

    def _send_discord(self, plan: DeliveryPlan) -> DeliveryResult:
        interaction_id = plan.meta.get("interaction_id")
        interaction_token = plan.meta.get("interaction_token")
        if interaction_id and interaction_token:
            url = f"https://discord.com/api/v10/interactions/{interaction_id}/{interaction_token}/callback"
            return self._post_json(
                url,
                plan.body,
                headers=plan.headers,
                platform="discord",
                mode=plan.mode,
                target=plan.target,
            )
        url = self.config.delivery.platform_base_urls.get("discord", "")
        if not url:
            token = self.config.delivery.platform_tokens.get("discord", "")
            if not token:
                return DeliveryResult(success=False, platform="discord", mode=plan.mode, target=plan.target, error="discord webhook url or interaction token missing", request_body=plan.body)
            url = f"https://discord.com/api/webhooks/{token}"
        return self._post_json(url, plan.body, headers=plan.headers, platform="discord", mode=plan.mode, target=plan.target)

    def _send_telegram(self, plan: DeliveryPlan) -> DeliveryResult:
        token = self.config.delivery.platform_tokens.get("telegram", "")
        base_url = self.config.delivery.platform_base_urls.get("telegram", "").rstrip("/")
        if not base_url:
            if not token:
                return DeliveryResult(success=False, platform="telegram", mode=plan.mode, target=plan.target, error="telegram bot token missing", request_body=plan.body)
            base_url = f"https://api.telegram.org/bot{token}"
        if "/bot" not in base_url and token:
            base_url = f"{base_url.rstrip('/')}/bot{token}"
        url = f"{base_url.rstrip('/')}/sendMessage"
        return self._post_json(url, plan.body, headers=plan.headers, platform="telegram", mode=plan.mode, target=plan.target)

    def _send_whatsapp(self, plan: DeliveryPlan) -> DeliveryResult:
        token = self.config.delivery.platform_tokens.get("whatsapp", "")
        phone_number_id = plan.body.get("phone_number_id") or self.config.delivery.platform_tokens.get("whatsapp_phone_number_id", "")
        base_url = self.config.delivery.platform_base_urls.get("whatsapp", "").rstrip("/")
        if not base_url:
            base_url = "https://graph.facebook.com/v19.0"
        if phone_number_id:
            url = f"{base_url}/{phone_number_id}/messages"
        else:
            url = f"{base_url}/messages"
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self._post_json(url, plan.body, headers=headers, platform="whatsapp", mode=plan.mode, target=plan.target)

    def _send_signal(self, plan: DeliveryPlan) -> DeliveryResult:
        base_url = self.config.delivery.platform_base_urls.get("signal", "http://127.0.0.1:8080").rstrip("/")
        url = f"{base_url}/v1/send"
        payload = {
            "message": plan.body.get("message", ""),
        }
        recipient = plan.body.get("recipient")
        group_id = plan.body.get("group_id")
        if recipient:
            payload["number"] = recipient
        if group_id:
            payload["groupId"] = group_id
        return self._post_json(url, payload, headers=plan.headers, platform="signal", mode=plan.mode, target=plan.target)

    def _send_mattermost(self, plan: DeliveryPlan) -> DeliveryResult:
        url = plan.url or self.config.delivery.platform_base_urls.get("mattermost", "")
        if not url:
            token = self.config.delivery.platform_tokens.get("mattermost", "")
            base = self.config.delivery.platform_base_urls.get("mattermost_api", "").rstrip("/")
            if token and base:
                url = f"{base}/api/v4/posts"
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
                return self._post_json(url, plan.body, headers=headers, platform="mattermost", mode=plan.mode, target=plan.target)
            return DeliveryResult(success=False, platform="mattermost", mode=plan.mode, target=plan.target, error="mattermost url/token missing", request_body=plan.body)
        return self._post_json(url, plan.body, headers=plan.headers, platform="mattermost", mode=plan.mode, target=plan.target)

    def _send_matrix(self, plan: DeliveryPlan) -> DeliveryResult:
        base_url = self.config.delivery.platform_base_urls.get("matrix", "").rstrip("/")
        token = self.config.delivery.platform_tokens.get("matrix", "")
        room_id = plan.target
        if not base_url or not token:
            return DeliveryResult(success=False, platform="matrix", mode=plan.mode, target=plan.target, error="matrix base url or token missing", request_body=plan.body)
        txn_id = uuid.uuid4().hex
        url = f"{base_url}/_matrix/client/v3/rooms/{urllib.parse.quote(room_id, safe='')}/send/m.room.message/{txn_id}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {k: v for k, v in plan.body.items() if v is not None}
        if "m.relates_to" in payload and payload["m.relates_to"] is None:
            payload.pop("m.relates_to", None)
        return self._post_json(url, payload, headers=headers, platform="matrix", mode=plan.mode, target=plan.target)

    def _send_email(self, plan: DeliveryPlan) -> DeliveryResult:
        cfg = self.config.delivery
        if not cfg.smtp_host:
            return DeliveryResult(success=False, platform="email", mode=plan.mode, target=plan.target, error="smtp host missing", request_body=plan.body)
        msg = email.message.EmailMessage()
        msg["To"] = plan.body.get("to", plan.target)
        msg["From"] = cfg.default_from_email or cfg.smtp_username or "kx-agent@localhost"
        msg["Subject"] = plan.body.get("subject", "KX Agent reply")
        if plan.body.get("in_reply_to"):
            msg["In-Reply-To"] = str(plan.body["in_reply_to"])
        msg.set_content(plan.body.get("text", ""))
        context = ssl.create_default_context()
        try:
            if cfg.smtp_use_tls:
                with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.timeout_seconds) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=context)
                    smtp.ehlo()
                    if cfg.smtp_username:
                        smtp.login(cfg.smtp_username, cfg.smtp_password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=cfg.timeout_seconds) as smtp:
                    smtp.ehlo()
                    if cfg.smtp_username:
                        smtp.login(cfg.smtp_username, cfg.smtp_password)
                    smtp.send_message(msg)
        except Exception as exc:
            return DeliveryResult(success=False, platform="email", mode=plan.mode, target=plan.target, error=str(exc), request_body=plan.body)
        return DeliveryResult(success=True, platform="email", mode=plan.mode, target=plan.target, request_body=plan.body)

    def _send_sms(self, plan: DeliveryPlan) -> DeliveryResult:
        cfg = self.config.delivery
        if not cfg.twilio_account_sid or not cfg.twilio_auth_token or not cfg.twilio_from_number:
            return DeliveryResult(success=False, platform="sms", mode=plan.mode, target=plan.target, error="twilio credentials missing", request_body=plan.body)
        url = f"https://api.twilio.com/2010-04-01/Accounts/{cfg.twilio_account_sid}/Messages.json"
        form = urllib.parse.urlencode(
            {
                "To": plan.body.get("to", plan.target),
                "From": cfg.twilio_from_number,
                "Body": plan.body.get("body", ""),
            }
        ).encode("utf-8")
        auth = base64.b64encode(f"{cfg.twilio_account_sid}:{cfg.twilio_auth_token}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        return self._request(url, form, headers=headers, method="POST", platform="sms", mode=plan.mode, target=plan.target, request_body=plan.body)

    def _send_dingtalk(self, plan: DeliveryPlan) -> DeliveryResult:
        url = plan.url or self.config.delivery.platform_base_urls.get("dingtalk", "")
        if not url:
            return DeliveryResult(success=False, platform="dingtalk", mode=plan.mode, target=plan.target, error="dingtalk webhook missing", request_body=plan.body)
        return self._post_json(url, plan.body, headers=plan.headers, platform="dingtalk", mode=plan.mode, target=plan.target)

    def _send_feishu(self, plan: DeliveryPlan) -> DeliveryResult:
        base_url = self.config.delivery.platform_base_urls.get("feishu", "").rstrip("/") or "https://open.feishu.cn"
        token = self.config.delivery.platform_tokens.get("feishu", "")
        if not token:
            if plan.url:
                return self._post_json(plan.url, plan.body, headers=plan.headers, platform="feishu", mode=plan.mode, target=plan.target)
            return DeliveryResult(success=False, platform="feishu", mode=plan.mode, target=plan.target, error="feishu token missing", request_body=plan.body)
        url = f"{base_url}/open-apis/im/v1/messages?receive_id_type=open_id"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}
        payload = {
            "receive_id": plan.body.get("receive_id") or plan.target,
            "msg_type": plan.body.get("msg_type", "text"),
            "content": json.dumps(plan.body.get("content") or {"text": ""}, ensure_ascii=False),
        }
        return self._post_json(url, payload, headers=headers, platform="feishu", mode=plan.mode, target=plan.target)

    def _send_wecom(self, plan: DeliveryPlan) -> DeliveryResult:
        url = plan.url or self.config.delivery.platform_base_urls.get("wecom", "")
        if not url:
            return DeliveryResult(success=False, platform="wecom", mode=plan.mode, target=plan.target, error="wecom webhook missing", request_body=plan.body)
        return self._post_json(url, plan.body, headers=plan.headers, platform="wecom", mode=plan.mode, target=plan.target)

    def _send_wecom_callback(self, plan: DeliveryPlan) -> DeliveryResult:
        url = plan.url or self.config.delivery.platform_base_urls.get("wecom_callback", "")
        if not url:
            return DeliveryResult(success=False, platform="wecom_callback", mode=plan.mode, target=plan.target, error="wecom_callback webhook missing", request_body=plan.body)
        return self._post_json(url, plan.body, headers=plan.headers, platform="wecom_callback", mode=plan.mode, target=plan.target)

    def _send_weixin(self, plan: DeliveryPlan) -> DeliveryResult:
        url = plan.url or self.config.delivery.platform_base_urls.get("weixin", "")
        if not url:
            return DeliveryResult(success=False, platform="weixin", mode=plan.mode, target=plan.target, error="weixin webhook missing", request_body=plan.body)
        return self._post_json(url, plan.body, headers=plan.headers, platform="weixin", mode=plan.mode, target=plan.target)

    def _send_bluebubbles(self, plan: DeliveryPlan) -> DeliveryResult:
        url = plan.url or self.config.delivery.platform_base_urls.get("bluebubbles", "")
        if not url:
            return DeliveryResult(success=False, platform="bluebubbles", mode=plan.mode, target=plan.target, error="bluebubbles webhook missing", request_body=plan.body)
        return self._post_json(url, plan.body, headers=plan.headers, platform="bluebubbles", mode=plan.mode, target=plan.target)

    def _send_qqbot(self, plan: DeliveryPlan) -> DeliveryResult:
        url = plan.url or self.config.delivery.platform_base_urls.get("qqbot", "")
        if not url:
            return DeliveryResult(success=False, platform="qqbot", mode=plan.mode, target=plan.target, error="qqbot endpoint missing", request_body=plan.body)
        return self._post_json(url, plan.body, headers=plan.headers, platform="qqbot", mode=plan.mode, target=plan.target)

    def _send_yuanbao(self, plan: DeliveryPlan) -> DeliveryResult:
        url = plan.url or self.config.delivery.platform_base_urls.get("yuanbao", "")
        if not url:
            return self._dry_run(plan, "yuanbao gateway not configured")
        return self._post_json(url, plan.body, headers=plan.headers, platform="yuanbao", mode=plan.mode, target=plan.target)

    def _request(
        self,
        url: str,
        raw_body: bytes,
        *,
        headers: dict[str, str],
        method: str,
        platform: str,
        mode: str,
        target: str,
        request_body: dict[str, Any],
    ) -> DeliveryResult:
        request = urllib.request.Request(url, data=raw_body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.config.delivery.timeout_seconds) as resp:
                body_text = resp.read().decode("utf-8", errors="replace")
                parsed_json = None
                try:
                    parsed = json.loads(body_text)
                    if isinstance(parsed, dict):
                        parsed_json = parsed
                except Exception:
                    parsed_json = None
                return DeliveryResult(
                    success=200 <= resp.status < 300,
                    platform=platform,
                    mode=mode,
                    target=target,
                    url=url,
                    status_code=resp.status,
                    response_text=body_text,
                    response_json=parsed_json,
                    request_body=request_body,
                )
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return DeliveryResult(
                success=False,
                platform=platform,
                mode=mode,
                target=target,
                url=url,
                status_code=exc.code,
                response_text=body_text,
                error=str(exc),
                request_body=request_body,
            )
        except Exception as exc:
            return DeliveryResult(
                success=False,
                platform=platform,
                mode=mode,
                target=target,
                url=url,
                error=str(exc),
                request_body=request_body,
            )

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str],
        platform: str,
        mode: str,
        target: str,
    ) -> DeliveryResult:
        body = json.dumps({k: v for k, v in payload.items() if v is not None}, ensure_ascii=False).encode("utf-8")
        merged_headers = {"Content-Type": "application/json; charset=utf-8"}
        merged_headers.update(headers or {})
        return self._request(
            url,
            body,
            headers=merged_headers,
            method="POST",
            platform=platform,
            mode=mode,
            target=target,
            request_body=payload,
        )
