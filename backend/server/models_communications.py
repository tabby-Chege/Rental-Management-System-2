from datetime import datetime, timezone

from server.extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class PropertyConversation(db.Model):
    __tablename__ = "property_conversations"
    __table_args__ = (
        db.UniqueConstraint(
            "property_id", "tenant_user_id", name="uq_property_conversation_tenant"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(
        db.Integer, db.ForeignKey("properties.id"), nullable=False, index=True
    )
    tenant_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)


class PropertyMessage(db.Model):
    __tablename__ = "property_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("property_conversations.id"),
        nullable=False,
        index=True,
    )
    sender_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    body = db.Column(db.String(5000), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender_user_id": self.sender_user_id,
            "body": self.body,
            "created_at": self.created_at.isoformat(),
        }
