import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models import AgentMessage

class AgentMessageBus:
    """
    Asynchronous and synchronous Agent Message Bus.
    Enforces FIPA-style performative communication between agents:
    - REQUEST: Ask an agent to perform an action or make a decision.
    - AGREE: Confirm agreement to execute the requested action.
    - REFUSE: Reject the request with explicit, documented reasons.
    - PROPOSE: Counter-propose usable alternatives when request cannot be met.
    - INFORM: Broadcast or notify fact/state change.
    - FAILURE: Inform that execution failed unexpectedly.
    
    All exchanged messages are stored in `agent_messages` table for complete
    traceability on the Organiser Dashboard.
    """
    def __init__(self):
        self._agents: Dict[str, Any] = {}

    def register_agent(self, agent) -> None:
        self._agents[agent.name] = agent

    def get_agent(self, name: str):
        return self._agents.get(name)

    def log_message(
        self,
        db: Session,
        conversation_id: str,
        sender: str,
        receiver: str,
        performative: str,
        content: Dict[str, Any]
    ) -> AgentMessage:
        record = AgentMessage(
            conversation_id=conversation_id,
            sender=sender,
            receiver=receiver,
            performative=performative,
            content=content,
            timestamp=datetime.utcnow()
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def send(
        self,
        db: Session,
        sender: str,
        receiver: str,
        performative: str,
        content: Dict[str, Any],
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a point-to-point message from sender to receiver.
        """
        if not conversation_id:
            conversation_id = f"conv-{uuid.uuid4().hex[:10]}"

        # 1. Log the outgoing message
        self.log_message(
            db=db,
            conversation_id=conversation_id,
            sender=sender,
            receiver=receiver,
            performative=performative,
            content=content
        )

        # 2. Locate destination agent
        target_agent = self._agents.get(receiver)
        if not target_agent:
            failure_reply = {
                "conversation_id": conversation_id,
                "sender": "MessageBus",
                "receiver": sender,
                "performative": "FAILURE",
                "content": {"error": f"Agent '{receiver}' is not registered on the bus."},
                "timestamp": datetime.utcnow().isoformat()
            }
            self.log_message(
                db=db,
                conversation_id=conversation_id,
                sender="MessageBus",
                receiver=sender,
                performative="FAILURE",
                content=failure_reply["content"]
            )
            return failure_reply

        # 3. Deliver to agent handler
        incoming_payload = {
            "conversation_id": conversation_id,
            "sender": sender,
            "receiver": receiver,
            "performative": performative,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }

        reply = target_agent.handle_message(db=db, message=incoming_payload, bus=self)

        # 4. If reply returned, ensure conversation_id matches and log reply
        if reply and isinstance(reply, dict):
            reply_conv_id = reply.get("conversation_id", conversation_id)
            reply_sender = reply.get("sender", receiver)
            reply_receiver = reply.get("receiver", sender)
            reply_perf = reply.get("performative", "INFORM")
            reply_content = reply.get("content", {})

            self.log_message(
                db=db,
                conversation_id=reply_conv_id,
                sender=reply_sender,
                receiver=reply_receiver,
                performative=reply_perf,
                content=reply_content
            )

        return reply

    def broadcast(
        self,
        db: Session,
        sender: str,
        performative: str,
        content: Dict[str, Any],
        conversation_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Broadcast an INFORM message to all registered agents (e.g. NotificationAgent).
        """
        if not conversation_id:
            conversation_id = f"conv-bc-{uuid.uuid4().hex[:8]}"

        replies = []
        for name, agent in self._agents.items():
            if name != sender:
                # Log broadcast leg
                self.log_message(
                    db=db,
                    conversation_id=conversation_id,
                    sender=sender,
                    receiver=name,
                    performative=performative,
                    content=content
                )
                msg = {
                    "conversation_id": conversation_id,
                    "sender": sender,
                    "receiver": name,
                    "performative": performative,
                    "content": content,
                    "timestamp": datetime.utcnow().isoformat()
                }
                try:
                    res = agent.handle_message(db=db, message=msg, bus=self)
                    if res:
                        replies.append(res)
                except Exception as e:
                    pass
        return replies

# Global singleton message bus instance
message_bus = AgentMessageBus()
