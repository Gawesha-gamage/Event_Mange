# IT4123 Agent Based Computing Practical — ICA 02
## Architectural Design & Verification Report: EventSphere Multi-Agent Ticketing & Venue Platform

**Module:** IT4123 Agent Based Computing Practical  
**System Name:** EventSphere  
**Date:** November 2026  

---

## 1. Executive Summary & System Overview

**EventSphere** is an autonomous, multi-agent venue booking and digital ticketing platform engineered for a university ecosystem. It replaces traditional monolithic database-centric booking logic with a distributed **Multi-Agent System (MAS)** where every operational decision—including event scheduling, calendar clash detection, seat reservations, admission verification, and waitlist allocations—is made through asynchronous cooperation among software agents.

The application is built with a **FastAPI (Python 3.12)** backend, **SQLAlchemy ORM** supporting SQLite (local development) and PostgreSQL (production deployment), and an interactive **mobile-first web interface** responsive down to 375px phone screen width without requiring native application downloads.

---

## 2. Multi-Agent System (MAS) Architecture

To distinguish EventSphere from ordinary database CRUD applications, all agent interactions adhere to the following principles:
1. **Messages, not method calls:** Agents communicate solely through structured JSON messages routed through a central `AgentMessageBus`. Agents never invoke one another's internal Python methods directly.
2. **Standard Performatives:** Every message uses standard FIPA communication performatives:
   - `REQUEST`: Ask an agent to perform an action or evaluate a request.
   - `AGREE`: Confirm agreement to execute an action.
   - `REFUSE`: Reject a request with documented, explicit reasons.
   - `PROPOSE`: Counter-propose usable alternatives when a request cannot be met.
   - `INFORM`: Broadcast or notify agents/users of state transitions.
   - `FAILURE`: Notify of unexpected operational failure.
3. **Persistent Beliefs:** Agents maintain belief state in an `agent_beliefs` table, ensuring memory across application restarts.
4. **End-to-End Traceability:** Every message is cataloged with a unique `conversation_id`, viewable on the Organiser Admin Dashboard to trace a single user action across multiple agents.

```
                           +----------------------+
                           |   AgentMessageBus    |
                           +----------+-----------+
                                      |
         +-------------------+--------+--------+-------------------+
         |                   |                 |                   |
+--------v----------+ +------v--------+ +------v----------+ +------v-----------+
|    VenueAgent     | | BookingAgent  | |   TicketAgent   | |  WaitlistAgent   |
| (Turnaround Clash)| | (Fair Selling)| | (Admit Once/QR) | | (Holds & Sweeps) |
+--------+----------+ +------+--------+ +------+----------+ +------+-----------+
         |                   |                 |                   |
         +-------------------+--------+--------+-------------------+
                                      |
                           +----------v-----------+
                           |  NotificationAgent   |
                           | (In-App & Email Log) |
                           +----------------------+
```

---

## 3. Detailed Agent Specifications & Documented Rules

### 3.1. VenueAgent
* **Designated Goal:** Keep every venue's calendar free of clashes and manage venue bookings.
* **Persistent Beliefs:** Turnaround buffer duration, venue peak hours, private hire conditions.
* **Documented Decision Rules:**
  - `Rule VA-1`: Two activities at the same venue must maintain at least a **60-minute turnaround buffer**. Any overlap within `[start - 60m, end + 60m]` is refused (`REFUSE`).
  - `Rule VA-2`: Requests exceeding venue maximum capacity are immediately refused.
  - `Rule VA-3`: Venues marked closed for private hire cannot accept hire requests.
  - `Rule VA-4`: Private hire pricing applies base hourly rate $\times$ duration, plus a **25% weekend surcharge** and a **20% peak evening surcharge (18:00–23:00)**.
  - `Rule VA-5`: Routine private hire requests (guests $\le$ 100 and cost $\le$ £1,000) are confirmed automatically (`AGREE`).
  - `Rule VA-6`: High-scale private hire requests (guests $>$ 100 or cost $>$ £1,000) are escalated to human administrators (`INFORM`/escalated).
  - `Rule VA-7`: When a requested slot clashes, the agent computes and returns **usable alternatives** (`PROPOSE`), offering offset times and other campus venues with sufficient capacity.

### 3.2. BookingAgent
* **Designated Goal:** Sell tickets fairly without overselling and enforce booking/refund rules.
* **Persistent Beliefs:** Ticket purchase quotas, cancellation policy thresholds, active cart holds.
* **Documented Decision Rules:**
  - `Rule BA-1`: Maximum **6 tickets** per booking transaction to prevent hoarding and ensure fair public access.
  - `Rule BA-2`: Ticket reservation uses atomic conditional decrement; overselling is physically prohibited at the database level.
  - `Rule BA-3`: Event must be in `published` status and end time must be in the future.
  - `Rule BA-4 (Stated Refund Policy)`:
    - Cancellation $\ge$ 48 hours prior to event start: **100% full refund** (`AGREE`).
    - Cancellation between 24 and 48 hours prior: **50% partial refund** (`AGREE`).
    - Cancellation $<$ 24 hours prior: **0% refund** (`REFUSE`).
  - `Rule BA-5`: Cancellation of an event by organisers mandates **100% full refund** for all confirmed tickets.
  - `Rule BA-6`: When tickets are cancelled, freed seats are immediately reported to `WaitlistAgent` via `INFORM`.

### 3.3. TicketAgent
* **Designated Goal:** Admit each ticket exactly once and prevent fraudulent reuse.
* **Persistent Beliefs:** Issued ticket registry, suspicious repeated scan counter surviving restarts.
* **Documented Decision Rules:**
  - `Rule TA-1`: Every digital ticket is provisioned with an unguessable cryptographic token and embedded SVG QR code.
  - `Rule TA-2`: A ticket is admitted strictly once; `scanned_at` is set and status is marked `used`.
  - `Rule TA-3`: Second scan of an admitted ticket is refused as `already_used`.
  - `Rule TA-4`: Scanning at the gate of another event is refused as `wrong_event`.
  - `Rule TA-5`: Cancelled tickets or tickets for cancelled events are refused as `cancelled`.
  - `Rule TA-6`: Check-in window opens 3 hours prior to event start.
  - `Rule TA-7 (Suspicious Scan Detection)`: Multiple scans of an already admitted ticket trigger an alert on the staff scanner for potential shared screenshot fraud.

### 3.4. WaitlistAgent
* **Designated Goal:** Pass freed seats to waiting customers fairly, hold them for a time limit, and re-offer on expiry.
* **Persistent Beliefs:** Waitlist queue order, active hold expirations, total expiry sweep iterations.
* **Documented Decision Rules:**
  - `Rule WA-1`: Seats are re-allocated strictly in FIFO order based on waitlist timestamp.
  - `Rule WA-2`: Waiting attendees receive a **5-minute timed hold** to claim the freed seat.
  - `Rule WA-3 (Proactive Autonomous Behavior)`: A background scheduler acts on a periodic timer without human intervention, sweeping expired holds.
  - `Rule WA-4`: Expired seats are automatically revoked and cascaded to the next waiting customer.
  - `Rule WA-5`: If the waitlist queue is exhausted, seats are returned to general inventory.

### 3.5. NotificationAgent
* **Designated Goal:** Tell the right person what affects them.
* **Persistent Beliefs:** Outbound message dispatch metrics, broadcast event counters.
* **Documented Decision Rules:**
  - `Rule NA-1`: User-targeted messages are converted into persistent in-app notifications.
  - `Rule NA-2`: Critical booking confirmations and seat hold offers trigger simulated SMTP email delivery logging.
  - `Rule NA-3 (Reactive Behavior)`: Listens for system-wide broadcast `INFORM` events and aggregates audit intelligence.

---

## 4. Concurrency & Overbooking Prevention

A critical technical requirement is ensuring that two simultaneous requests for the final remaining seat cannot oversell the event.

### Implementation Strategy
Rather than relying on application-level checks which are vulnerable to race conditions, EventSphere implements **database-level atomic conditional updates**:

```python
rows_updated = db.query(TicketCategory).filter(
    TicketCategory.id == cat_id,
    TicketCategory.remaining_quantity >= quantity
).update(
    {TicketCategory.remaining_quantity: TicketCategory.remaining_quantity - quantity},
    synchronize_session="fetch"
)
```

1. The check `remaining_quantity >= quantity` and the decrement `remaining_quantity - quantity` occur in a single atomic database instruction.
2. In a scenario with 1 seat remaining and two concurrent booking requests $R_1$ and $R_2$:
   - The first request to execute acquires the database row lock, updates `remaining_quantity` from 1 to 0, and returns `rows_updated = 1`.
   - The second request executes against `remaining_quantity = 0`, failing the `WHERE` condition, and returns `rows_updated = 0`.
3. `BookingAgent` detects `rows_updated == 0` and sends a `REFUSE` performative with `can_join_waitlist = True`.

This behavior was validated via multithreaded concurrency tests (`test_booking_concurrency.py`).

---

## 5. Part C — Advanced Features Verification

All 8 optional advanced features from Part C have been implemented and tested:

1. **Waitlist with Timed Seat Holds & Visible Countdown:** Attendee portal renders an interactive live countdown for offered seats with 1-click claim checkout.
2. **Weekend & Peak-Time Venue Pricing:** `VenueAgent` autonomously evaluates booking timestamps, applying +25% weekend and +20% evening multipliers.
3. **Detection of Suspicious Repeated Scans:** `TicketAgent` tracks scan counters; scanning an admitted ticket 2+ times triggers a fraud warning on the staff screen.
4. **Agents Reachable Over HTTP:** Each agent exposes a public HTTP inbox (`POST /api/agents/{agent_name}/inbox`) accepting JSON messages with Swagger documentation.
5. **Email Notifications:** Dispatched and logged by `NotificationAgent` upon ticket issuance and hold allocations.
6. **Dashboard Visual Charts:** Organiser Hub renders interactive Chart.js bar and doughnut graphs for sales, check-ins, and ticket statuses.
7. **5-Minute Cart Holds:** Attendees entering checkout receive a temporary 5-minute inventory lock with visible countdown.
8. **Advanced Search:** Multi-attribute filtering across date range, venue, price range, category, and keyword.

---

## 6. Verification & Test Suite Summary

The automated test suite in `tests/` contains **12 comprehensive Pytest test cases**:

| Test Case | Area Tested | Result |
| :--- | :--- | :--- |
| `test_http_agent_inbox_endpoints` | Part C HTTP Agent Inboxes & Documented Rules | **PASSED** |
| `test_venue_agent_turnaround_buffer_clash` | VenueAgent 60m Turnaround Buffer & Clashes | **PASSED** |
| `test_venue_agent_pricing_and_counter_proposal` | VenueAgent Peak/Weekend Pricing & Counter-Proposals | **PASSED** |
| `test_booking_agent_max_tickets_and_stated_refunds`| BookingAgent Max 6 Rule & Stated Refund Policy | **PASSED** |
| `test_ticket_agent_issue_and_unique_qr` | TicketAgent Unique Tokens & SVG QR Generation | **PASSED** |
| `test_waitlist_agent_queue_and_proactive_sweep` | WaitlistAgent Timed Holds & Proactive Expiry Sweep | **PASSED** |
| `test_notification_agent_reactive_broadcast` | NotificationAgent In-App, Email & Reactive INFORM | **PASSED** |
| `test_user_registration_and_password_hashing` | Accounts Registration & Hashed Passwords | **PASSED** |
| `test_role_enforcement_admin_and_staff` | Role Enforcement on Admin & Scanner Endpoints | **PASSED** |
| `test_overbooking_prevention_under_concurrency` | Multithreaded Overbooking Prevention | **PASSED** |
| `test_ticket_admit_once_and_double_checkin_prevention`| Single Admission & Double Check-in Rejection | **PASSED** |
| `test_ticket_wrong_event_and_cancelled_rejection` | Gate Check-in for Wrong/Cancelled Tickets | **PASSED** |

---

## 7. Viva Demo Accounts & Deployment Reference

### Demo Accounts

| Role | Email | Password |
| :--- | :--- | :--- |
| **Admin Organiser** | `admin@eventsphere.ac.uk` | `Admin@123` |
| **Gate Staff** | `staff@eventsphere.ac.uk` | `Staff@123` |
| **Attendee (Student)** | `attendee@eventsphere.ac.uk` | `Attendee@123` |

### Cloud Deployment
- **Deployment Platform:** Render (or compatible cloud host with HTTPS)
- **Configuration Files:** `render.yaml`, `Procfile`, `Dockerfile`, `docker-compose.yml`
- **Application URL:** Configurable via Render public URL (HTTPS enabled)
- **Repository:** Ready for GitHub repository submission
