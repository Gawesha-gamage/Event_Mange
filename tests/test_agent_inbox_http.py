import pytest
from app.routers.agent_inbox import list_active_agents, agent_http_inbox
from app.schemas import AgentMessageSchema

def test_http_agent_inbox_endpoints(db):
    """
    Part C Advanced Feature Test:
    Agents reachable over HTTP: an inbox endpoint per agent accepting JSON messages,
    documented in API docs.
    """
    # 1. List active agents and endpoints
    agents = list_active_agents()
    assert len(agents) >= 5
    agent_names = [a["name"] for a in agents]
    assert "VenueAgent" in agent_names
    assert "BookingAgent" in agent_names
    assert "TicketAgent" in agent_names
    assert "WaitlistAgent" in agent_names
    assert "NotificationAgent" in agent_names

    # Check documented decision rules are exposed
    venue_agent_info = next(a for a in agents if a["name"] == "VenueAgent")
    assert len(venue_agent_info["decision_rules"]) >= 5
    assert venue_agent_info["inbox_endpoint"] == "/api/agents/VenueAgent/inbox"

    # 2. Post structured JSON message directly to BookingAgent inbox
    message_payload = AgentMessageSchema(
        conversation_id="conv-http-test-01",
        sender="ExternalHTTPTester",
        receiver="BookingAgent",
        performative="REQUEST",
        content={
            "action": "book_tickets",
            "quantity": 10 # Exceeds max 6 tickets rule
        }
    )
    reply = agent_http_inbox(agent_name="BookingAgent", message_payload=message_payload, db=db)
    assert reply["conversation_id"] == "conv-http-test-01"
    assert reply["sender"] == "BookingAgent"
    assert reply["performative"] == "REFUSE"
    assert "capped at 6 tickets" in reply["content"]["reason"]
