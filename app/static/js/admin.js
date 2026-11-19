/**
 * EventSphere - Organiser Dashboard & Admin Controller
 * Analytics, CRUD, Multi-Agent Message Bus Logs, and Beliefs Inspector
 */

let eventsChartInstance = null;
let statusChartInstance = null;

document.addEventListener("DOMContentLoaded", () => {
    // Check role
    const user = AuthState.getUser();
    if (!user || user.role !== "admin") {
        showToast("Access restricted: Admin role required", "danger");
        setTimeout(() => window.location.href = "/", 1500);
        return;
    }

    loadDashboardOverview();
    loadDashboardCharts();
    loadAdminVenues();
    loadAdminEvents();
    loadEscalatedHires();
    loadAgentLogs();
    loadAgentBeliefs();
    setupLogFilters();
});

// ----------------------------------------------------
// 1. Dashboard Overview & KPI Metrics
// ----------------------------------------------------
async function loadDashboardOverview() {
    try {
        const stats = await apiRequest("/api/dashboard/stats");
        document.getElementById("kpi-events").textContent = stats.total_events;
        document.getElementById("kpi-venues").textContent = stats.total_venues;
        document.getElementById("kpi-tickets").textContent = stats.total_tickets_sold;
        document.getElementById("kpi-revenue").textContent = `£${stats.total_simulated_revenue.toFixed(2)}`;
        document.getElementById("kpi-checkins").textContent = stats.total_checkins;
        document.getElementById("kpi-escalations").textContent = stats.active_hire_requests;

        // Render Events Performance Table
        const tbody = document.getElementById("admin-events-perf-tbody");
        if (tbody) {
            tbody.innerHTML = stats.events_overview.map(e => `
                <tr>
                    <td class="fw-bold">${e.title}</td>
                    <td class="text-muted small">${e.venue_name}</td>
                    <td>${e.tickets_sold} / ${e.capacity}</td>
                    <td><span class="badge bg-primary-subtle text-primary">${e.attendance_rate}</span></td>
                    <td class="fw-bold text-success">£${e.simulated_revenue.toFixed(2)}</td>
                    <td><span class="badge ${e.status === 'published' ? 'bg-success' : 'bg-secondary'}">${e.status.toUpperCase()}</span></td>
                </tr>
            `).join("");
        }
    } catch (err) {
        showToast("Failed to load metrics: " + err.message, "danger");
    }
}

// ----------------------------------------------------
// 2. Visual Charts (Chart.js - Part C)
// ----------------------------------------------------
async function loadDashboardCharts() {
    try {
        const chartsData = await apiRequest("/api/dashboard/charts");

        // 1. Bar Chart: Sales vs Check-ins vs Capacity
        const ctxEvents = document.getElementById("chart-events");
        if (ctxEvents && typeof Chart !== "undefined") {
            if (eventsChartInstance) eventsChartInstance.destroy();
            eventsChartInstance = new Chart(ctxEvents, {
                type: "bar",
                data: {
                    labels: chartsData.events_chart.labels,
                    datasets: [
                        {
                            label: "Capacity",
                            data: chartsData.events_chart.capacities,
                            backgroundColor: "rgba(226, 232, 240, 0.8)",
                            borderRadius: 4
                        },
                        {
                            label: "Tickets Sold",
                            data: chartsData.events_chart.sales,
                            backgroundColor: "rgba(79, 70, 229, 0.85)",
                            borderRadius: 4
                        },
                        {
                            label: "Admitted",
                            data: chartsData.events_chart.checkins,
                            backgroundColor: "rgba(16, 185, 129, 0.85)",
                            borderRadius: 4
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: "top" } },
                    scales: { y: { beginAtZero: true } }
                }
            });
        }

        // 2. Doughnut Chart: Ticket Status Distribution
        const ctxStatus = document.getElementById("chart-ticket-status");
        if (ctxStatus && typeof Chart !== "undefined") {
            if (statusChartInstance) statusChartInstance.destroy();
            statusChartInstance = new Chart(ctxStatus, {
                type: "doughnut",
                data: {
                    labels: chartsData.ticket_status_chart.labels,
                    datasets: [{
                        data: chartsData.ticket_status_chart.data,
                        backgroundColor: ["#4f46e5", "#10b981", "#ef4444"]
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: "bottom" } }
                }
            });
        }
    } catch (e) {}
}

// ----------------------------------------------------
// 3. Multi-Agent Message Bus Log Explorer (Part B & C)
// ----------------------------------------------------
async function loadAgentLogs(filters = {}) {
    const container = document.getElementById("agent-logs-container");
    if (!container) return;

    try {
        const params = new URLSearchParams();
        if (filters.conversation_id) params.append("conversation_id", filters.conversation_id);
        if (filters.sender) params.append("sender", filters.sender);
        if (filters.receiver) params.append("receiver", filters.receiver);
        if (filters.performative) params.append("performative", filters.performative);

        const logs = await apiRequest(`/api/dashboard/agent-logs?${params.toString()}`);
        if (!logs || logs.length === 0) {
            container.innerHTML = '<div class="alert alert-light text-center py-4">No agent messages logged for this filter.</div>';
            return;
        }

        container.innerHTML = logs.map(m => {
            const time = new Date(m.timestamp).toLocaleTimeString();
            return `
                <div class="agent-log-item ${m.performative}">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <div>
                            <span class="badge ${getPerfBadgeClass(m.performative)} me-1">${m.performative}</span>
                            <span class="badge bg-dark badge-agent">${m.sender}</span>
                            <i class="bi bi-arrow-right mx-1 text-muted"></i>
                            <span class="badge bg-secondary badge-agent">${m.receiver}</span>
                        </div>
                        <small class="text-muted">${time} • <a href="#" onclick="filterByConvId('${m.conversation_id}'); return false;">${m.conversation_id}</a></small>
                    </div>
                    <pre class="bg-light p-2 rounded mb-0 text-dark small" style="white-space: pre-wrap; font-size: 0.78rem;">${JSON.stringify(m.content, null, 2)}</pre>
                </div>
            `;
        }).join("");
    } catch (err) {
        container.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
    }
}

function getPerfBadgeClass(p) {
    switch (p) {
        case "REQUEST": return "bg-primary";
        case "AGREE": return "bg-success";
        case "REFUSE": return "bg-danger";
        case "PROPOSE": return "bg-warning text-dark";
        case "INFORM": return "bg-purple text-dark border";
        default: return "bg-secondary";
    }
}

function setupLogFilters() {
    const convInput = document.getElementById("filter-log-conv");
    const perfSelect = document.getElementById("filter-log-perf");
    if (convInput) {
        convInput.addEventListener("input", () => {
            loadAgentLogs({
                conversation_id: convInput.value.trim(),
                performative: perfSelect?.value
            });
        });
    }
    if (perfSelect) {
        perfSelect.addEventListener("change", () => {
            loadAgentLogs({
                conversation_id: convInput?.value.trim(),
                performative: perfSelect.value
            });
        });
    }
}

function filterByConvId(convId) {
    const input = document.getElementById("filter-log-conv");
    if (input) {
        input.value = convId;
        loadAgentLogs({ conversation_id: convId });
    }
}

// ----------------------------------------------------
// 4. Persistent Agent Beliefs Inspector
// ----------------------------------------------------
async function loadAgentBeliefs() {
    const container = document.getElementById("agent-beliefs-tbody");
    if (!container) return;

    try {
        const beliefs = await apiRequest("/api/dashboard/agent-beliefs");
        if (!beliefs || beliefs.length === 0) {
            container.innerHTML = '<tr><td colspan="4" class="text-muted text-center">No persistent beliefs initialized yet.</td></tr>';
            return;
        }

        container.innerHTML = beliefs.map(b => `
            <tr>
                <td class="fw-bold font-monospace">${b.agent_name}</td>
                <td class="font-monospace text-primary">${b.belief_key}</td>
                <td><code class="small text-dark">${JSON.stringify(b.belief_value)}</code></td>
                <td class="small text-muted">${new Date(b.updated_at).toLocaleTimeString()}</td>
            </tr>
        `).join("");
    } catch (e) {}
}

// ----------------------------------------------------
// 5. Venue Management (Admin CRUD)
// ----------------------------------------------------
async function loadAdminVenues() {
    const tbody = document.getElementById("admin-venues-tbody");
    if (!tbody) return;

    try {
        const venues = await apiRequest("/api/venues");
        tbody.innerHTML = venues.map(v => `
            <tr>
                <td class="fw-bold">${v.name}</td>
                <td>${v.location}</td>
                <td>${v.capacity}</td>
                <td>£${v.hourly_rate.toFixed(2)}/hr</td>
                <td><span class="badge ${v.is_open_for_private_hire ? 'bg-success' : 'bg-secondary'}">${v.is_open_for_private_hire ? 'Yes' : 'No'}</span></td>
                <td>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteVenue(${v.id})"><i class="bi bi-trash"></i></button>
                </td>
            </tr>
        `).join("");
    } catch (e) {}
}

async function createNewVenue(e) {
    if (e) e.preventDefault();
    const payload = {
        name: document.getElementById("venue-name").value.trim(),
        location: document.getElementById("venue-location").value.trim(),
        capacity: parseInt(document.getElementById("venue-capacity").value),
        hourly_rate: parseFloat(document.getElementById("venue-rate").value),
        description: document.getElementById("venue-desc").value.trim(),
        is_open_for_private_hire: document.getElementById("venue-open-hire").checked
    };

    try {
        await apiRequest("/api/venues", {
            method: "POST",
            body: JSON.stringify(payload)
        });
        showToast("Venue registered successfully!", "success");
        const modal = bootstrap.Modal.getInstance(document.getElementById("createVenueModal"));
        if (modal) modal.hide();
        loadAdminVenues();
    } catch (err) {
        showToast("Failed to create venue: " + err.message, "danger");
    }
}

async function deleteVenue(id) {
    if (!confirm("Are you sure you want to remove this venue?")) return;
    try {
        await apiRequest(`/api/venues/${id}`, { method: "DELETE" });
        showToast("Venue removed.", "info");
        loadAdminVenues();
    } catch (e) {
        showToast(e.message, "danger");
    }
}

// ----------------------------------------------------
// 6. Event Management (Admin CRUD & Turnaround Buffer)
// ----------------------------------------------------
async function loadAdminEvents() {
    const tbody = document.getElementById("admin-events-list-tbody");
    if (!tbody) return;

    try {
        const events = await apiRequest("/api/events?status_filter=all");
        tbody.innerHTML = events.map(e => `
            <tr>
                <td class="fw-bold">${e.title}</td>
                <td>${e.venue_name || 'N/A'}</td>
                <td class="small">${new Date(e.start_time).toLocaleString()}</td>
                <td><span class="badge ${e.status === 'published' ? 'bg-success' : 'bg-danger'}">${e.status.toUpperCase()}</span></td>
                <td>
                    ${e.status === 'published' ? `
                        <button class="btn btn-sm btn-outline-danger" onclick="cancelEventAdmin(${e.id})">
                            <i class="bi bi-x-circle me-1"></i>Cancel Event
                        </button>
                    ` : '<span class="text-muted small">Cancelled</span>'}
                </td>
            </tr>
        `).join("");
    } catch (e) {}
}

async function createNewEvent(e) {
    if (e) e.preventDefault();
    const categories = [];
    const catRows = document.querySelectorAll(".ticket-category-row");
    catRows.forEach(row => {
        const name = row.querySelector(".cat-name").value.trim();
        const price = parseFloat(row.querySelector(".cat-price").value) || 0;
        const qty = parseInt(row.querySelector(".cat-qty").value) || 10;
        if (name) categories.push({ name, price, total_quantity: qty });
    });

    const payload = {
        title: document.getElementById("event-title").value.trim(),
        category: document.getElementById("event-category").value,
        venue_id: parseInt(document.getElementById("event-venue-select").value),
        start_time: document.getElementById("event-start").value,
        end_time: document.getElementById("event-end").value,
        description: document.getElementById("event-desc").value.trim(),
        image_url: document.getElementById("event-image").value.trim(),
        ticket_categories: categories
    };

    try {
        await apiRequest("/api/events", {
            method: "POST",
            body: JSON.stringify(payload)
        });
        showToast("Event validated by VenueAgent and published!", "success");
        const modal = bootstrap.Modal.getInstance(document.getElementById("createEventModal"));
        if (modal) modal.hide();
        loadAdminEvents();
        loadDashboardOverview();
        loadAgentLogs();
    } catch (err) {
        showToast("Event rejected: " + err.message, "danger");
    }
}

async function cancelEventAdmin(eventId) {
    if (!confirm("Are you sure you want to cancel this event? BookingAgent will immediately issue 100% full refunds for all booked tickets!")) return;
    try {
        const res = await apiRequest(`/api/events/${eventId}/cancel`, { method: "POST" });
        showToast("Event cancelled and full refunds issued!", "info");
        loadAdminEvents();
        loadDashboardOverview();
        loadAgentLogs();
    } catch (err) {
        showToast(err.message, "danger");
    }
}

// ----------------------------------------------------
// 7. Escalated Private Hire Approvals
// ----------------------------------------------------
async function loadEscalatedHires() {
    const tbody = document.getElementById("escalated-hires-tbody");
    if (!tbody) return;

    try {
        const hires = await apiRequest("/api/venue-hire?status_filter=escalated");
        if (!hires || hires.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No pending escalations. All routine hires confirmed autonomously by VenueAgent!</td></tr>';
            return;
        }

        tbody.innerHTML = hires.map(h => `
            <tr>
                <td class="fw-bold">${h.venue_name}</td>
                <td>${h.attendee_name} (${h.attendee_email})</td>
                <td>${h.purpose}</td>
                <td><span class="badge bg-warning text-dark">${h.guest_count} guests</span></td>
                <td class="fw-bold text-primary">£${h.calculated_price.toFixed(2)}</td>
                <td class="small text-muted">${h.decision_reason}</td>
                <td>
                    <button class="btn btn-sm btn-success me-1" onclick="handleHireDecision(${h.id}, 'approve')"><i class="bi bi-check-lg"></i></button>
                    <button class="btn btn-sm btn-danger" onclick="handleHireDecision(${h.id}, 'reject')"><i class="bi bi-x-lg"></i></button>
                </td>
            </tr>
        `).join("");
    } catch (e) {}
}

async function handleHireDecision(id, action) {
    try {
        await apiRequest(`/api/venue-hire/${id}/action`, {
            method: "POST",
            body: JSON.stringify({ action })
        });
        showToast(`Hire request ${action}d successfully.`, "success");
        loadEscalatedHires();
        loadAgentLogs();
    } catch (err) {
        showToast(err.message, "danger");
    }
}
