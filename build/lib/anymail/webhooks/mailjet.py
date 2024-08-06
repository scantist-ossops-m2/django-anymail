import json
from datetime import datetime

from django.utils.timezone import utc

from .base import AnymailBaseWebhookView
from ..signals import tracking, AnymailTrackingEvent, EventType, RejectReason


class MailjetTrackingWebhookView(AnymailBaseWebhookView):
    """Handler for Mailjet delivery and engagement tracking webhooks"""

    signal = tracking

    def parse_events(self, request):
        esp_events = json.loads(request.body.decode('utf-8'))
        return [self.esp_to_anymail_event(esp_event) for esp_event in esp_events]

    # https://dev.mailjet.com/guides/#events
    event_types = {
        # Map Mailjet event: Anymail normalized type
        'sent': EventType.DELIVERED,  # accepted by receiving MTA
        'open': EventType.OPENED,
        'click': EventType.CLICKED,
        'bounce': EventType.BOUNCED,
        'blocked': EventType.REJECTED,
        'spam': EventType.COMPLAINED,
        'unsub': EventType.UNSUBSCRIBED,
    }

    reject_reasons = {
        # Map Mailjet error strings to Anymail normalized reject_reason
        # error_related_to: recipient
        'user unknown': RejectReason.BOUNCED,
        'mailbox inactive': RejectReason.BOUNCED,
        'quota exceeded': RejectReason.BOUNCED,
        'blacklisted': RejectReason.BLOCKED,  # might also be previous unsubscribe
        'spam reporter': RejectReason.SPAM,
        # error_related_to: domain
        'invalid domain': RejectReason.BOUNCED,
        'no mail host': RejectReason.BOUNCED,
        'relay/access denied': RejectReason.BOUNCED,
        'greylisted': RejectReason.OTHER,  # see special handling below
        'typofix': RejectReason.INVALID,
        # error_related_to: spam (all Mailjet policy/filtering; see above for spam complaints)
        'sender blocked': RejectReason.BLOCKED,
        'content blocked': RejectReason.BLOCKED,
        'policy issue': RejectReason.BLOCKED,
        # error_related_to: mailjet
        'preblocked': RejectReason.BLOCKED,
        'duplicate in campaign': RejectReason.OTHER,
    }

    def esp_to_anymail_event(self, esp_event):
        event_type = self.event_types.get(esp_event['event'], EventType.UNKNOWN)
        if esp_event.get('error', None) == 'greylisted' and not esp_event.get('hard_bounce', False):
            # "This is a temporary error due to possible unrecognised senders. Delivery will be re-attempted."
            event_type = EventType.DEFERRED

        try:
            timestamp = datetime.fromtimestamp(esp_event['time'], tz=utc)
        except (KeyError, ValueError):
            timestamp = None

        try:
            # convert bigint MessageID to str to match backend AnymailRecipientStatus
            message_id = str(esp_event['MessageID'])
        except (KeyError, TypeError):
            message_id = None

        if 'error' in esp_event:
            reject_reason = self.reject_reasons.get(esp_event['error'], RejectReason.OTHER)
        else:
            reject_reason = None

        tag = esp_event.get('customcampaign', None)
        tags = [tag] if tag else []

        try:
            metadata = json.loads(esp_event['Payload'])
        except (KeyError, ValueError):
            metadata = {}

        return AnymailTrackingEvent(
            event_type=event_type,
            timestamp=timestamp,
            message_id=message_id,
            event_id=None,
            recipient=esp_event.get('email', None),
            reject_reason=reject_reason,
            mta_response=esp_event.get('smtp_reply', None),
            tags=tags,
            metadata=metadata,
            click_url=esp_event.get('url', None),
            user_agent=esp_event.get('agent', None),
            esp_event=esp_event,
        )
