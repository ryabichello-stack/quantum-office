import uuid
from datetime import datetime, timezone

from app.models.conversation import Conversation
from app.models.lead import Lead
from app.services.conversation_present import (
    channel_label,
    filter_conversation_items,
    mask_phone,
    serialize_conversation_item,
)


def test_mask_phone_ru_mobile():
    assert mask_phone("+79211234567") == "+7 921 ••• •• 67"


def test_channel_label_phone():
    assert channel_label("phone") == "Входящий звонок"
    assert channel_label("web") == "Чат на сайте"
    assert channel_label("cabinet") == "Operator · кабинет"


def test_serialize_conversation_item_with_lead():
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        channel="widget",
        status="open",
        meta={"visitor_name": "Анна"},
        created_at=datetime.now(timezone.utc),
    )
    lead = Lead(
        id=uuid.uuid4(),
        tenant_id=conv.tenant_id,
        name="Анна Соколова",
        phone="+79211234567",
        source="widget",
    )
    item = serialize_conversation_item(conv, lead=lead, last_message=None)
    assert item["visitor_name"] == "Анна"
    assert item["visitor_phone_masked"] == "+7 921 ••• •• 67"
    assert item["is_new"] is True


def test_filter_conversation_items_search():
    items = [
        {"visitor_name": "Анна", "visitor_phone": "", "last_message_preview": "запись", "channel_label": "", "contact_ref": "", "is_new": True, "channel": "web"},
        {"visitor_name": "Борис", "visitor_phone": "", "last_message_preview": "цена", "channel_label": "", "contact_ref": "", "is_new": False, "channel": "web"},
    ]
    assert len(filter_conversation_items(items, q="анна")) == 1
    assert len(filter_conversation_items(items, status_filter="new")) == 1
