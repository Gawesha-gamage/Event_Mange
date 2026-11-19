import json
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import AgentBelief

class BaseAgent:
    """
    Abstract Base Class for EventSphere Autonomous Software Agents.
    Enforces clear goals, persistent beliefs/state across restarts,
    structured communication with performatives, and documented decision rules.
    """
    def __init__(self, name: str, goal: str):
        self.name = name
        self.goal = goal
        self.decision_rules = []

    def get_belief(self, db: Session, key: str, default: Any = None) -> Any:
        """Read a persistent belief from the database that survives server restarts."""
        record = db.query(AgentBelief).filter(
            AgentBelief.agent_name == self.name,
            AgentBelief.belief_key == key
        ).first()
        if record and record.belief_value is not None:
            return record.belief_value
        return default

    def set_belief(self, db: Session, key: str, value: Any) -> None:
        """Persist an agent's belief/state to the database."""
        record = db.query(AgentBelief).filter(
            AgentBelief.agent_name == self.name,
            AgentBelief.belief_key == key
        ).first()
        if not record:
            record = AgentBelief(
                agent_name=self.name,
                belief_key=key,
                belief_value=value
            )
            db.add(record)
        else:
            record.belief_value = value
            record.updated_at = datetime.utcnow()
        db.commit()

    def handle_message(self, db: Session, message: Dict[str, Any], bus) -> Dict[str, Any]:
        """
        Process an incoming structured agent message.
        Must return a response message with standard performative:
        AGREE, REFUSE, PROPOSE, INFORM, or FAILURE.
        """
        raise NotImplementedError("Subclasses must implement handle_message")
