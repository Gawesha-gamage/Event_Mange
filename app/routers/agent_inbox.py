from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, List

from app.database import get_db
from app.agents import message_bus
from app.schemas import AgentMessageSchema

router = APIRouter(prefix="/api/agents", tags=["HTTP Agent Inbox (Part C Advanced)"])

@router.get("", response_model=List[Dict[str, Any]])
def list_active_agents():
    """
    List all active autonomous software agents registered in EventSphere,
    including their designated goals and documented decision rules.
    """
    agents_info = []
    for name, agent in message_bus._agents.items():
        agents_info.append({
            "name": agent.name,
            "goal": agent.goal,
            "decision_rules": getattr(agent, "decision_rules", []),
            "inbox_endpoint": f"/api/agents/{agent.name}/inbox"
        })
    return agents_info

@router.post("/{agent_name}/inbox", response_model=Dict[str, Any])
def agent_http_inbox(
    agent_name: str,
    message_payload: AgentMessageSchema,
    db: Session = Depends(get_db)
):
    """
    Part C Advanced Feature:
    Agents reachable over HTTP. Each agent exposes an inbox endpoint accepting
    structured JSON messages carrying performatives:
    REQUEST, AGREE, REFUSE, PROPOSE, INFORM, FAILURE.
    """
    agent = message_bus.get_agent(agent_name)
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_name}' not found. Available agents: {list(message_bus._agents.keys())}"
        )

    response = message_bus.send(
        db=db,
        sender=message_payload.sender or "HTTPExternalClient",
        receiver=agent_name,
        performative=message_payload.performative or "REQUEST",
        content=message_payload.content,
        conversation_id=message_payload.conversation_id
    )

    return response
