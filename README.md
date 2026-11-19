# EventSphere - Multi-Agent Venue Booking & Digital Ticketing Platform
**IT4123 Agent Based Computing Practical — ICA 02**

EventSphere is an interactive, mobile-friendly venue booking and digital ticketing web platform built for a university campus. In EventSphere, every critical booking, clash check, seat allocation, admission check, and waitlist offer is decided autonomously by cooperating software agents communicating via structured JSON messages.

The platform is designed mobile-first (works down to 375px phone screen width), requires no mobile app installation, features a live camera QR ticket scanner with manual fallback, and is fully deployable to cloud hosts like Render.

---

## 👥 Demo Accounts for Viva Evaluation

EventSphere comes pre-seeded with 3 dedicated demo accounts with hashed passwords:

| Role | Name | Email | Password | Allowed Access |
| :--- | :--- | :--- | :--- | :--- |
| **Admin / Organiser** | Dr. Eleanor Vance | `admin@eventsphere.ac.uk` | `Admin@123` | Full Admin Hub, Organiser Analytics, Agent Message Bus Logs, Venue & Event CRUD, Hire Escalations |
| **Gate Staff** | Marcus Brody | `staff@eventsphere.ac.uk` | `Staff@123` | Gate Scanner (`/scanner`), Camera QR Reader, Manual Code Fallback, Suspicious Scan Alerts |
| **Attendee (Student)** | Sophie Turner | `attendee@eventsphere.ac.uk` | `Attendee@123` | Browse Events, Book Tickets, 5-Min Cart Hold, View Digital QR Tickets, Cancel & Refund, Waitlist, Private Hire |

> **Viva Shortcut:** The top bar includes a **"One-Click Demo Switcher"** to instantly log in as any role without typing!

---

## 🤖 Multi-Agent System (MAS) Architecture

EventSphere strictly adheres to multi-agent principles. Agents **do not call each other's functions directly**; instead, they exchange structured JSON messages carrying FIPA performatives over an asynchronous `AgentMessageBus`.

```
                        +----------------------+
                        |   AgentMessageBus    |
                        +----------+-----------+
                                   |
         +----------------+--------+--------+----------------+
         |                |                 |                |
+--------v-------+ +------v--------+ +------v-------+ +------v--------+
|   VenueAgent   | |  BookingAgent | |  TicketAgent | | WaitlistAgent |
+--------+-------+ +------+--------+ +------+-------+ +------+--------+
         |                |                 |                |
         +----------------+--------+--------+----------------+
                                   |
                        +----------v-----------+
                        |  NotificationAgent   |
                        +----------------------+
```

### Required Autonomous Agents

| Agent | Core Goal | Autonomous Decision Rules | Communicates With |
| :--- | :--- | :--- | :--- |
| **VenueAgent** | Keep every venue's calendar free of clashes | • 60-minute turnaround buffer between events (`Rule VA-1`)<br>• Capacity bounds verification (`Rule VA-2`)<br>• Private hire verification & peak/weekend pricing (`Rule VA-4`)<br>• Routine auto-confirmation vs. escalation (`Rule VA-5/6`)<br>• Counter-propose usable alternative slots/venues on clash (`Rule VA-7`) | NotificationAgent, Organiser Dashboard |
| **BookingAgent** | Sell tickets fairly without overselling | • Maximum 6 tickets per booking rule (`Rule BA-1`)<br>• Atomic database-level conditional update lock preventing overselling (`Rule BA-2`)<br>• Active 5-minute Cart Holds (`Part C`)<br>• Stated refund policy calculation (100% $\ge$ 48h, 50% 24–48h, 0% < 24h)<br>• Full 100% refund on event cancellation (`Rule BA-5`) | TicketAgent, WaitlistAgent, NotificationAgent |
| **TicketAgent** | Admit each ticket exactly once | • Issue unguessable cryptographic tokens & SVG QR codes (`Rule TA-1`)<br>• Single admission rule (`Rule TA-2`)<br>• Reject already used, wrong event, cancelled, or outside check-in time<br>• Detect suspicious repeated scans (possible shared screenshots / fraud) (`Rule TA-6`) | BookingAgent, Gate Scanner |
| **WaitlistAgent** | Pass freed seats to waiting customers | • FIFO priority queue for sold-out events (`Rule WA-1`)<br>• 5-minute timed seat hold offers (`Rule WA-2`)<br>• **Proactive Timer Sweep**: Autonomous background worker sweeps expired holds and cascades seats to next waiting attendee without human intervention (`Rule WA-3/4`) | BookingAgent, NotificationAgent |
| **NotificationAgent** | Tell the right person what affects them | • Converts domain events into persistent in-app notifications (`Rule NA-1`)<br>• Dispatches and logs simulated outbound email notifications (`Rule NA-2`)<br>• Reactive broadcast listener for system-wide `INFORM` events (`Rule NA-3`) | All Agents (Broadcast Listener) |

---

## 🔒 Concurrency & Overbooking Prevention Approach

Under high concurrent load (e.g., hundreds of students clicking "Book" for the last remaining seat), standard ORM read-modify-write patterns suffer from race conditions leading to overselling.

EventSphere solves this using an **atomic database-level conditional update**:
```python
rows_updated = db.query(TicketCategory).filter(
    TicketCategory.id == cat_id,
    TicketCategory.remaining_quantity >= quantity
).update(
    {TicketCategory.remaining_quantity: TicketCategory.remaining_quantity - quantity},
    synchronize_session="fetch"
)
```
- The database engine atomically verifies `remaining_quantity >= quantity` in the same operation that performs the decrement.
- If two requests arrive simultaneously for the final ticket, exactly one transaction succeeds (`rows_updated = 1`), and the second transaction receives `rows_updated = 0`.
- The rejected request is gracefully handled by `BookingAgent` returning `REFUSE` with an invitation to join the priority waitlist.

---

## 🌟 Implemented Features

### Part A — Compulsory Functional Requirements
- [x] **Accounts & Roles:** Registration, sign-in, bcrypt-hashed passwords, role enforcement (admin, staff, attendee).
- [x] **Venue Management (Admin):** Create/edit venues with capacity, location, hourly rate, description, and private hire toggle.
- [x] **Event Management (Admin):** Multi-ticket categories (Standard, VIP, Student), turnaround buffer validation, publish/draft/cancel.
- [x] **Browsing & Booking (Attendee):** Mobile-friendly responsive catalog, category filters, live remaining tickets, simulated payments.
- [x] **Digital Tickets & Check-in:** Cryptographic unique QR codes, phone camera scanner (`html5-qrcode`), manual code fallback, double check-in prevention.
- [x] **Private Venue Hire:** Immediate decisions, automatic routine approval, counter-proposals with alternative slots/venues, admin escalations.
- [x] **Organiser Dashboard:** Revenue, tickets sold, check-in turnout rate, and multi-agent message log explorer.

### Part C — Advanced Features
1. [x] **Waitlist with Timed Seat Holds & Visible Countdown:** 5-minute reservation timer with 1-click claim.
2. [x] **Weekend and Peak-Time Venue Pricing:** VenueAgent automatically applies +25% weekend and +20% evening surcharges.
3. [x] **Suspicious Repeated Scan Detection:** Alerts staff when an admitted ticket is re-scanned repeatedly (fraud/screenshot sharing).
4. [x] **HTTP Agent Inbox Endpoints:** Every agent exposes an HTTP inbox (`/api/agents/{agent_name}/inbox`) accepting JSON messages.
5. [x] **Email Notifications:** Logged and dispatched asynchronously by NotificationAgent.
6. [x] **Visual Dashboard Charts:** Interactive Chart.js graphs (Sales vs. Check-ins vs. Capacity, and Ticket Status Distribution).
7. [x] **5-Minute Cart Holds:** Prevents cart snipping during simulated checkout with visible live countdown timer.
8. [x] **Advanced Search:** Multi-parameter filtering by date range, venue, price range, and keyword.

---

## 🚀 Quickstart: Running Locally

### 1. Prerequisites
- Python 3.11 or higher
- Git

### 2. Clone and Setup Environment
```bash
git clone <repository-url>
cd eventsphere

# Create virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Initialize & Seed Database
```bash
python seed_data.py
```

### 4. Run the Application
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
Open your browser and navigate to:
- **Attendee Portal:** `http://localhost:8000/`
- **Gate Staff Scanner:** `http://localhost:8000/scanner`
- **Organiser Admin Hub:** `http://localhost:8000/admin`
- **Interactive OpenAPI/Swagger Docs:** `http://localhost:8000/docs`

---

## 🧪 Running the Pytest Test Suite

The test suite contains **12 comprehensive tests** covering overbooking prevention under concurrency, double check-in rejection, and dedicated unit tests for all 5 agents:

```bash
python -m pytest tests/ -v
```

### Test Suite Summary:
```
tests/test_agent_inbox_http.py::test_http_agent_inbox_endpoints           PASSED
tests/test_agents.py::test_venue_agent_turnaround_buffer_clash            PASSED
tests/test_agents.py::test_venue_agent_pricing_and_counter_proposal       PASSED
tests/test_agents.py::test_booking_agent_max_tickets_and_stated_refunds   PASSED
tests/test_agents.py::test_ticket_agent_issue_and_unique_qr               PASSED
tests/test_agents.py::test_waitlist_agent_queue_and_proactive_sweep       PASSED
tests/test_agents.py::test_notification_agent_reactive_broadcast          PASSED
tests/test_auth_and_roles.py::test_user_registration_and_password_hashing PASSED
tests/test_auth_and_roles.py::test_role_enforcement_admin_and_staff       PASSED
tests/test_booking_concurrency.py::test_overbooking_prevention_under_concurrency PASSED
tests/test_ticket_checkin.py::test_ticket_admit_once_and_double_checkin_prevention PASSED
tests/test_ticket_checkin.py::test_ticket_wrong_event_and_cancelled_rejection PASSED
```

---

## ☁️ Deployment Guide (Render / Cloud Host)

EventSphere is packaged for 1-click cloud deployment:

### Deploying to Render
1. Push this repository to GitHub.
2. In [Render Dashboard](https://dashboard.render.com/), click **New +** $\rightarrow$ **Blueprint**.
3. Connect your GitHub repository. Render will automatically read `render.yaml`.
4. Render automatically runs `pip install -r requirements.txt`, seeds the database via `seed_data.py`, and starts the Uvicorn server on HTTPS!

### Docker Deployment
```bash
docker build -t eventsphere:latest .
docker run -p 8000:8000 eventsphere:latest
```
Or using Docker Compose:
```bash
docker-compose up --build
```
