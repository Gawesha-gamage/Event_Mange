/**
 * EventSphere - Attendee Portal Controller
 * Browsing, Booking, Digital Tickets, Venue Hire, and Waitlist
 */

let allVenues = [];
let activeCartHold = null;
let cartCountdownInterval = null;

document.addEventListener("DOMContentLoaded", () => {
    loadEvents();
    loadVenuesForHire();
    setupCategoryPills();
    setupSearchFilters();
});

// ----------------------------------------------------
// 1. Event Browsing & Advanced Search
// ----------------------------------------------------
async function loadEvents(filters = {}) {
    const listEl = document.getElementById("events-grid");
    if (!listEl) return;
    listEl.innerHTML = '<div class="col-12 text-center py-5"><div class="spinner-border text-primary"></div><p class="mt-2 text-muted">Consulting VenueAgent & BookingAgent...</p></div>';

    try {
        const params = new URLSearchParams();
        if (filters.search) params.append("search", filters.search);
        if (filters.category && filters.category !== "All") params.append("category", filters.category);
        if (filters.venue_id) params.append("venue_id", filters.venue_id);
        if (filters.min_price) params.append("min_price", filters.min_price);
        if (filters.max_price) params.append("max_price", filters.max_price);
        if (filters.start_date) params.append("start_date", filters.start_date);

        const events = await apiRequest(`/api/events?${params.toString()}`);
        renderEvents(events);
    } catch (err) {
        listEl.innerHTML = `<div class="col-12 alert alert-danger">Failed to load events: ${err.message}</div>`;
    }
}

function renderEvents(events) {
    const listEl = document.getElementById("events-grid");
    if (!events || events.length === 0) {
        listEl.innerHTML = `
            <div class="col-12 text-center py-5">
                <i class="bi bi-calendar-x fs-1 text-muted"></i>
                <h5 class="mt-3 text-secondary">No events found matching criteria</h5>
                <p class="text-muted small">Try clearing filters or searching for other keywords.</p>
            </div>
        `;
        return;
    }

    listEl.innerHTML = events.map(ev => {
        const startDate = new Date(ev.start_time);
        const dateStr = startDate.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
        const timeStr = startDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const isSoldOut = ev.total_remaining_tickets <= 0;
        const lowestPrice = ev.ticket_categories.length > 0 
            ? Math.min(...ev.ticket_categories.map(c => c.price)) 
            : 0;

        return `
            <div class="col-12 col-md-6 col-lg-4">
                <div class="event-card position-relative">
                    <div class="position-relative">
                        <img src="${ev.image_url || 'https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800&auto=format&fit=crop&q=60'}" 
                             alt="${ev.title}" class="event-card-img">
                        <span class="event-badge-category">${ev.category}</span>
                    </div>
                    <div class="p-3 d-flex flex-column flex-grow-1">
                        <div class="text-primary small fw-bold mb-1">
                            <i class="bi bi-calendar-event me-1"></i>${dateStr} • ${timeStr}
                        </div>
                        <h5 class="fw-bold text-dark mb-1 text-truncate">${ev.title}</h5>
                        <p class="text-muted small mb-2">
                            <i class="bi bi-geo-alt me-1 text-danger"></i>${ev.venue_name || 'University Venue'}
                        </p>
                        <p class="text-secondary small flex-grow-1" style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">
                            ${ev.description || 'Join us for this exciting university event.'}
                        </p>
                        <div class="d-flex align-items-center justify-content-between pt-2 border-top mt-2">
                            <div>
                                <small class="text-muted d-block">From</small>
                                <span class="fw-bold text-dark fs-5">£${lowestPrice.toFixed(2)}</span>
                            </div>
                            <div>
                                ${isSoldOut 
                                    ? `<button class="btn btn-warning btn-sm fw-bold px-3" onclick="openWaitlistModal(${ev.id})">
                                         <i class="bi bi-hourglass-split me-1"></i>Waitlist
                                       </button>`
                                    : `<button class="btn btn-primary btn-sm fw-bold px-3" onclick="openBookingModal(${ev.id})">
                                         Book Tickets
                                       </button>`
                                }
                            </div>
                        </div>
                        <div class="mt-2 text-end">
                            <small class="badge ${isSoldOut ? 'bg-danger' : 'bg-success-subtle text-success'}">
                                ${isSoldOut ? 'Sold Out' : `${ev.total_remaining_tickets} tickets left`}
                            </small>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join("");
}

function setupCategoryPills() {
    const pills = document.querySelectorAll(".category-pill");
    pills.forEach(pill => {
        pill.addEventListener("click", () => {
            pills.forEach(p => p.classList.remove("active"));
            pill.classList.add("active");
            const cat = pill.getAttribute("data-category");
            loadEvents({ category: cat });
        });
    });
}

function setupSearchFilters() {
    const searchInput = document.getElementById("search-input");
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener("input", () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                loadEvents({ search: searchInput.value.trim() });
            }, 300);
        });
    }

    const applyAdvBtn = document.getElementById("apply-advanced-filters");
    if (applyAdvBtn) {
        applyAdvBtn.addEventListener("click", () => {
            const filters = {
                search: document.getElementById("search-input")?.value.trim(),
                venue_id: document.getElementById("filter-venue")?.value,
                min_price: document.getElementById("filter-min-price")?.value,
                max_price: document.getElementById("filter-max-price")?.value,
                start_date: document.getElementById("filter-start-date")?.value
            };
            loadEvents(filters);
        });
    }
}

// ----------------------------------------------------
// 2. Booking Modal & Timed Cart Hold (Part C)
// ----------------------------------------------------
let currentBookingEvent = null;

async function openBookingModal(eventId) {
    if (!AuthState.isLoggedIn()) {
        AuthState.showLoginModal();
        showToast("Please sign in to book tickets", "warning");
        return;
    }

    try {
        currentBookingEvent = await apiRequest(`/api/events/${eventId}`);
        const modalEl = document.getElementById("bookingModal");
        document.getElementById("booking-event-title").textContent = currentBookingEvent.title;
        document.getElementById("booking-event-venue").textContent = `${currentBookingEvent.venue_name} (${currentBookingEvent.venue_location})`;
        document.getElementById("booking-event-time").textContent = new Date(currentBookingEvent.start_time).toLocaleString();

        const catSelect = document.getElementById("booking-category-select");
        catSelect.innerHTML = currentBookingEvent.ticket_categories.map(cat => `
            <option value="${cat.id}" data-price="${cat.price}" data-remaining="${cat.remaining_quantity}" ${cat.remaining_quantity <= 0 ? 'disabled' : ''}>
                ${cat.name} - £${cat.price.toFixed(2)} (${cat.remaining_quantity} available)
            </option>
        `).join("");

        updateBookingSummary();
        new bootstrap.Modal(modalEl).show();
    } catch (err) {
        showToast("Failed to open booking: " + err.message, "danger");
    }
}

function updateBookingSummary() {
    const select = document.getElementById("booking-category-select");
    const qtyInput = document.getElementById("booking-quantity-input");
    const selectedOpt = select.options[select.selectedIndex];
    if (!selectedOpt) return;

    const price = parseFloat(selectedOpt.getAttribute("data-price") || 0);
    const qty = parseInt(qtyInput.value) || 1;
    const total = (price * qty).toFixed(2);
    document.getElementById("booking-summary-total").textContent = `£${total}`;
}

// Start 5-minute Cart Hold
async function proceedToSimulatedPayment() {
    const catId = parseInt(document.getElementById("booking-category-select").value);
    const qty = parseInt(document.getElementById("booking-quantity-input").value);

    try {
        const holdData = await apiRequest("/api/bookings/hold", {
            method: "POST",
            body: JSON.stringify({ ticket_category_id: catId, quantity: qty })
        });

        activeCartHold = holdData;
        document.getElementById("booking-step-1").classList.add("d-none");
        document.getElementById("booking-step-2").classList.remove("d-none");
        document.getElementById("simulated-pay-amount").textContent = document.getElementById("booking-summary-total").textContent;

        // Start visible countdown timer
        startCartCountdown(holdData.seconds_remaining);
        showToast("5-Minute Cart Hold active! Complete payment before it expires.", "success");
    } catch (err) {
        showToast("Hold refused: " + err.message, "danger");
    }
}

function startCartCountdown(seconds) {
    clearInterval(cartCountdownInterval);
    let remaining = seconds;
    const timerEl = document.getElementById("cart-countdown-timer");

    function renderTime() {
        const m = Math.floor(remaining / 60);
        const s = remaining % 60;
        timerEl.textContent = `${m}:${s < 10 ? '0' : ''}${s}`;
        if (remaining <= 0) {
            clearInterval(cartCountdownInterval);
            showToast("Cart hold expired! Seats released back.", "danger");
            resetBookingModal();
        }
        remaining--;
    }
    renderTime();
    cartCountdownInterval = setInterval(renderTime, 1000);
}

function resetBookingModal() {
    clearInterval(cartCountdownInterval);
    activeCartHold = null;
    document.getElementById("booking-step-1").classList.remove("d-none");
    document.getElementById("booking-step-2").classList.add("d-none");
    const modal = bootstrap.Modal.getInstance(document.getElementById("bookingModal"));
    if (modal) modal.hide();
}

async function confirmSimulatedPayment() {
    if (!activeCartHold) return;
    const btn = document.getElementById("btn-confirm-payment");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Confirming with BookingAgent...';

    try {
        const res = await apiRequest("/api/bookings", {
            method: "POST",
            body: JSON.stringify({
                ticket_category_id: activeCartHold.ticket_category_id,
                quantity: activeCartHold.quantity,
                cart_hold_id: activeCartHold.hold_id,
                cardholder_name: document.getElementById("cardholder-name").value || "Simulated User",
                payment_method: "simulated_card"
            })
        });

        clearInterval(cartCountdownInterval);
        resetBookingModal();
        showToast(`Booking ${res.booking_reference} confirmed! Digital tickets issued.`, "success");
        loadEvents();
        switchMainTab("tickets-tab");
        loadMyTickets();
    } catch (err) {
        showToast("Booking failed: " + err.message, "danger");
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Complete Simulated Payment';
    }
}

// ----------------------------------------------------
// 3. Digital Tickets with QR Codes (Part A & C)
// ----------------------------------------------------
async function loadMyTickets() {
    if (!AuthState.isLoggedIn()) return;
    const container = document.getElementById("my-tickets-container");
    if (!container) return;
    container.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary"></div></div>';

    try {
        const tickets = await apiRequest("/api/tickets/my");
        if (!tickets || tickets.length === 0) {
            container.innerHTML = `
                <div class="col-12 text-center py-5">
                    <i class="bi bi-ticket-perforated fs-1 text-muted"></i>
                    <h5 class="mt-3 text-secondary">No digital tickets issued yet</h5>
                    <p class="text-muted small">Book tickets for university events to view your entrance QR codes here.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = tickets.map(t => {
            const isUsed = t.status === "used";
            const isCancelled = t.status === "cancelled";
            const badgeClass = isUsed ? "bg-secondary" : isCancelled ? "bg-danger" : "bg-success";
            const statusLabel = isUsed ? "Admitted / Used" : isCancelled ? "Cancelled" : "Valid for Admission";

            return `
                <div class="col-12 col-md-6 col-lg-4">
                    <div class="ticket-container">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <span class="badge ${badgeClass}">${statusLabel}</span>
                            <small class="fw-bold text-muted">${t.unique_code}</small>
                        </div>
                        <h5 class="fw-bold text-dark mb-1">${t.event_title}</h5>
                        <p class="text-muted small mb-2"><i class="bi bi-geo-alt me-1 text-danger"></i>${t.venue_name}</p>
                        <p class="text-primary small fw-semibold mb-3">
                            <i class="bi bi-clock me-1"></i>${new Date(t.start_time).toLocaleString()}
                        </p>
                        
                        <div class="qr-display my-2 text-center">
                            ${t.qr_code_svg || '<i class="bi bi-qr-code fs-1"></i>'}
                        </div>
                        <p class="text-center text-muted small mt-2 mb-0">Show this QR code at the entrance scanner.</p>
                    </div>
                </div>
            `;
        }).join("");
    } catch (err) {
        container.innerHTML = `<div class="col-12 alert alert-danger">${err.message}</div>`;
    }
}

// ----------------------------------------------------
// 4. Booking History & Refund Cancellation
// ----------------------------------------------------
async function loadMyBookings() {
    if (!AuthState.isLoggedIn()) return;
    const container = document.getElementById("my-bookings-container");
    if (!container) return;
    container.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';

    try {
        const bookings = await apiRequest("/api/bookings/my");
        if (!bookings || bookings.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-4">No booking records found.</p>';
            return;
        }

        container.innerHTML = bookings.map(b => {
            const isCancelled = b.status === "cancelled";
            return `
                <div class="card border mb-3 shadow-sm">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div>
                                <h6 class="fw-bold mb-0 text-primary">${b.booking_reference}</h6>
                                <small class="text-muted">${new Date(b.created_at).toLocaleString()}</small>
                            </div>
                            <span class="badge ${isCancelled ? 'bg-danger' : 'bg-success'}">${b.status.toUpperCase()}</span>
                        </div>
                        <h5 class="fw-bold text-dark">${b.event_title}</h5>
                        <p class="small text-muted mb-2">
                            Venue: ${b.venue_name || 'N/A'} • Total: <strong>£${b.total_amount.toFixed(2)}</strong> (Ref: ${b.payment_reference})
                        </p>
                        ${isCancelled ? `
                            <div class="alert alert-warning py-2 small mb-0">
                                <strong>Refund Processed:</strong> £${b.refund_amount.toFixed(2)}
                            </div>
                        ` : `
                            <div class="d-flex justify-content-between align-items-center mt-3 pt-2 border-top">
                                <small class="text-muted"><i class="bi bi-shield-check me-1"></i>Stated Refund Policy applies</small>
                                <button class="btn btn-outline-danger btn-sm" onclick="cancelBooking(${b.id})">
                                    Cancel & Refund
                                </button>
                            </div>
                        `}
                    </div>
                </div>
            `;
        }).join("");
    } catch (err) {
        container.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
    }
}

async function cancelBooking(bookingId) {
    if (!confirm("Are you sure you want to cancel this booking? Refund will be calculated strictly based on university policy (100% >=48h, 50% 24-48h, 0% <24h).")) return;

    try {
        const res = await apiRequest(`/api/bookings/${bookingId}/cancel`, { method: "POST" });
        showToast(`Booking cancelled. Refund: £${res.refund_amount.toFixed(2)} (${res.refund_percentage}%). ${res.message}`, "info");
        loadMyBookings();
        loadMyTickets();
        loadEvents();
    } catch (err) {
        showToast("Cancellation failed: " + err.message, "danger");
    }
}

// ----------------------------------------------------
// 5. Private Venue Hire (Part A & C)
// ----------------------------------------------------
async function loadVenuesForHire() {
    try {
        allVenues = await apiRequest("/api/venues");
        const select = document.getElementById("hire-venue-select");
        if (select) {
            select.innerHTML = allVenues
                .filter(v => v.is_open_for_private_hire)
                .map(v => `<option value="${v.id}" data-rate="${v.hourly_rate}" data-capacity="${v.capacity}">${v.name} (Cap: ${v.capacity}, £${v.hourly_rate}/hr)</option>`)
                .join("");
            recalcHirePrice();
        }

        const filterVenue = document.getElementById("filter-venue");
        if (filterVenue) {
            filterVenue.innerHTML = '<option value="">All Venues</option>' + allVenues.map(v => `<option value="${v.id}">${v.name}</option>`).join("");
        }
    } catch (e) {}
}

function recalcHirePrice() {
    const select = document.getElementById("hire-venue-select");
    const startInput = document.getElementById("hire-start-time");
    const endInput = document.getElementById("hire-end-time");
    const guestsInput = document.getElementById("hire-guest-count");
    const previewEl = document.getElementById("hire-price-preview");
    if (!select || !startInput || !endInput || !previewEl) return;

    const opt = select.options[select.selectedIndex];
    if (!opt || !startInput.value || !endInput.value) {
        previewEl.innerHTML = '<span class="text-muted">Select venue, dates, and times to calculate quote.</span>';
        return;
    }

    const rate = parseFloat(opt.getAttribute("data-rate") || 100);
    const start = new Date(startInput.value);
    const end = new Date(endInput.value);
    const guests = parseInt(guestsInput.value) || 1;

    if (end <= start) {
        previewEl.innerHTML = '<span class="text-danger">End time must be after start time.</span>';
        return;
    }

    const hours = Math.max(1, (end - start) / 3600000);
    const isWeekend = start.getDay() === 0 || start.getDay() === 6;
    const isPeak = start.getHours() >= 18;
    let multiplier = 1.0;
    if (isWeekend) multiplier *= 1.25;
    if (isPeak) multiplier *= 1.20;

    const base = hours * rate;
    const total = (base * multiplier) + (guests > 80 ? 50 : 0);

    previewEl.innerHTML = `
        <div class="alert alert-info py-2 mb-0 small">
            <div>Estimated Duration: <strong>${hours.toFixed(1)} hrs</strong> at £${rate}/hr</div>
            ${isWeekend ? '<span class="badge bg-purple text-dark border me-1">Weekend (+25%)</span>' : ''}
            ${isPeak ? '<span class="badge bg-warning text-dark me-1">Peak Evening (+20%)</span>' : ''}
            ${guests > 80 ? '<span class="badge bg-secondary me-1">Large Crowd Clean Fee (£50)</span>' : ''}
            <div class="fw-bold fs-6 mt-1 text-primary">Estimated Total: £${total.toFixed(2)}</div>
        </div>
    `;
}

async function submitVenueHireRequest(e) {
    if (e) e.preventDefault();
    if (!AuthState.isLoggedIn()) {
        AuthState.showLoginModal();
        return;
    }

    const venueId = parseInt(document.getElementById("hire-venue-select").value);
    const startTime = document.getElementById("hire-start-time").value;
    const endTime = document.getElementById("hire-end-time").value;
    const purpose = document.getElementById("hire-purpose").value.trim();
    const guestCount = parseInt(document.getElementById("hire-guest-count").value);

    const btn = document.getElementById("btn-submit-hire");
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Consulting VenueAgent...';

    try {
        const res = await apiRequest("/api/venue-hire", {
            method: "POST",
            body: JSON.stringify({
                venue_id: venueId,
                start_time: startTime,
                end_time: endTime,
                purpose: purpose,
                guest_count: guestCount
            })
        });

        const resultBox = document.getElementById("hire-decision-result");
        resultBox.classList.remove("d-none");

        if (res.status === "counter_proposal") {
            // PROPOSE performative with usable alternatives!
            const alts = res.counter_proposal || {};
            const slotsHtml = (alts.suggested_slots || []).map(s => `
                <li class="mb-1">
                    <strong>${s.label}:</strong> ${new Date(s.start_time).toLocaleString()}
                </li>
            `).join("");
            const venuesHtml = (alts.available_venues || []).map(v => `
                <li class="mb-1">
                    <strong>${v.name}:</strong> Capacity ${v.capacity}, Price: £${v.calculated_price}
                </li>
            `).join("");

            resultBox.innerHTML = `
                <div class="alert alert-warning">
                    <h6 class="fw-bold"><i class="bi bi-arrow-repeat me-2"></i>VenueAgent Counter-Proposal</h6>
                    <p class="small mb-2">${res.decision_reason}</p>
                    <div class="bg-white p-2 rounded border small">
                        <strong>Available Alternative Times:</strong>
                        <ul class="mb-2 ps-3">${slotsHtml || 'None found on this date.'}</ul>
                        <strong>Alternative Venues with Capacity:</strong>
                        <ul class="mb-0 ps-3">${venuesHtml || 'None found.'}</ul>
                    </div>
                </div>
            `;
            showToast("Slot unavailable. Usable alternatives proposed by VenueAgent!", "warning");
        } else if (res.status === "confirmed") {
            resultBox.innerHTML = `
                <div class="alert alert-success">
                    <h6 class="fw-bold"><i class="bi bi-check-circle me-2"></i>Booking Confirmed Automatically!</h6>
                    <p class="small mb-0">Total Calculated: £${res.calculated_price.toFixed(2)}. ${res.decision_reason}</p>
                </div>
            `;
            showToast("Venue hire automatically confirmed by VenueAgent!", "success");
        } else if (res.status === "escalated") {
            resultBox.innerHTML = `
                <div class="alert alert-info">
                    <h6 class="fw-bold"><i class="bi bi-hourglass-split me-2"></i>Escalated for Admin Approval</h6>
                    <p class="small mb-0">${res.decision_reason}</p>
                </div>
            `;
            showToast("Request escalated for university admin approval.", "info");
        }
        loadMyHireRequests();
    } catch (err) {
        showToast("Venue hire request refused: " + err.message, "danger");
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Submit Hire Request';
    }
}

async function loadMyHireRequests() {
    if (!AuthState.isLoggedIn()) return;
    const container = document.getElementById("my-hire-requests-list");
    if (!container) return;

    try {
        const requests = await apiRequest("/api/venue-hire/my");
        if (!requests || requests.length === 0) {
            container.innerHTML = '<p class="text-muted small">No past hire requests.</p>';
            return;
        }

        container.innerHTML = requests.map(r => `
            <div class="list-group-item py-2">
                <div class="d-flex justify-content-between align-items-center">
                    <h6 class="mb-0 fw-bold">${r.venue_name} - ${r.purpose}</h6>
                    <span class="badge ${r.status === 'confirmed' || r.status === 'approved' ? 'bg-success' : r.status === 'escalated' ? 'bg-info' : 'bg-warning text-dark'}">
                        ${r.status.toUpperCase()}
                    </span>
                </div>
                <small class="text-muted d-block">
                    ${new Date(r.start_time).toLocaleString()} to ${new Date(r.end_time).toLocaleTimeString()} • ${r.guest_count} guests • £${r.calculated_price.toFixed(2)}
                </small>
                <small class="text-secondary">${r.decision_reason || ''}</small>
            </div>
        `).join("");
    } catch (e) {}
}

// ----------------------------------------------------
// 6. Waitlist & Countdown Claim (Part C Advanced)
// ----------------------------------------------------
async function openWaitlistModal(eventId) {
    if (!AuthState.isLoggedIn()) {
        AuthState.showLoginModal();
        return;
    }

    try {
        const ev = await apiRequest(`/api/events/${eventId}`);
        const modalEl = document.getElementById("waitlistModal");
        document.getElementById("waitlist-event-title").textContent = ev.title;
        const catSelect = document.getElementById("waitlist-category-select");
        catSelect.innerHTML = ev.ticket_categories.map(c => `
            <option value="${c.id}">${c.name} (£${c.price.toFixed(2)})</option>
        `).join("");
        new bootstrap.Modal(modalEl).show();
    } catch (err) {
        showToast(err.message, "danger");
    }
}

async function submitJoinWaitlist() {
    const catId = parseInt(document.getElementById("waitlist-category-select").value);
    const qty = parseInt(document.getElementById("waitlist-quantity").value) || 1;

    try {
        const res = await apiRequest("/api/waitlist/join", {
            method: "POST",
            body: JSON.stringify({ ticket_category_id: catId, requested_quantity: qty })
        });
        showToast(res.message || "Joined waitlist successfully!", "success");
        const modal = bootstrap.Modal.getInstance(document.getElementById("waitlistModal"));
        if (modal) modal.hide();
        switchMainTab("waitlist-tab");
        loadMyWaitlist();
    } catch (err) {
        showToast("Waitlist request refused: " + err.message, "danger");
    }
}

let waitlistTimers = {};

async function loadMyWaitlist() {
    if (!AuthState.isLoggedIn()) return;
    const container = document.getElementById("my-waitlist-container");
    if (!container) return;
    container.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';

    // Clear active timers
    Object.values(waitlistTimers).forEach(clearInterval);
    waitlistTimers = {};

    try {
        const entries = await apiRequest("/api/waitlist/my");
        if (!entries || entries.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-4">You are not currently on any event waitlists.</p>';
            return;
        }

        container.innerHTML = entries.map(e => {
            const isOffered = e.status === "offered";
            return `
                <div class="card border mb-3 shadow-sm ${isOffered ? 'border-warning' : ''}">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <div>
                                <h5 class="fw-bold mb-0 text-dark">${e.event_title}</h5>
                                <small class="text-muted">${e.category_name} (Qty: ${e.requested_quantity})</small>
                            </div>
                            <span class="badge ${isOffered ? 'bg-warning text-dark' : e.status === 'waiting' ? 'bg-info' : 'bg-secondary'}">
                                ${e.status.toUpperCase()}
                            </span>
                        </div>

                        ${isOffered ? `
                            <div class="countdown-box my-3">
                                <div>
                                    <div class="fw-bold text-dark"><i class="bi bi-stopwatch me-1"></i>Seat Reserved For You!</div>
                                    <small class="text-muted">Claim before the proactive timer expires.</small>
                                </div>
                                <div class="countdown-timer" id="waitlist-timer-${e.id}">--:--</div>
                            </div>
                            <button class="btn btn-success fw-bold w-100" onclick="claimWaitlistSeat(${e.id}, ${e.ticket_category_id}, ${e.requested_quantity})">
                                <i class="bi bi-check-circle me-1"></i>Claim Held Seat & Complete Checkout
                            </button>
                        ` : `
                            <p class="small text-muted mb-0">Priority queue active. You will receive an instant notification when seats are freed.</p>
                        `}
                    </div>
                </div>
            `;
        }).join("");

        // Initialize countdowns for offered entries
        entries.forEach(e => {
            if (e.status === "offered" && e.seconds_remaining > 0) {
                let sec = e.seconds_remaining;
                const timerEl = document.getElementById(`waitlist-timer-${e.id}`);
                function update() {
                    if (!timerEl) return;
                    const m = Math.floor(sec / 60);
                    const s = sec % 60;
                    timerEl.textContent = `${m}:${s < 10 ? '0' : ''}${s}`;
                    if (sec <= 0) {
                        timerEl.textContent = "EXPIRED";
                        clearInterval(waitlistTimers[e.id]);
                        setTimeout(loadMyWaitlist, 1500);
                    }
                    sec--;
                }
                update();
                waitlistTimers[e.id] = setInterval(update, 1000);
            }
        });
    } catch (err) {
        container.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
    }
}

async function claimWaitlistSeat(entryId, catId, qty) {
    try {
        await apiRequest(`/api/waitlist/claim/${entryId}`, { method: "POST" });
        // Complete booking
        const res = await apiRequest("/api/bookings", {
            method: "POST",
            body: JSON.stringify({
                ticket_category_id: catId,
                quantity: qty,
                payment_method: "simulated_card"
            })
        });
        showToast("Held seat successfully claimed and booked!", "success");
        switchMainTab("tickets-tab");
        loadMyTickets();
    } catch (err) {
        showToast("Claim failed: " + err.message, "danger");
    }
}

// Tab navigation helper
function switchMainTab(tabId) {
    const triggerEl = document.getElementById(tabId);
    if (triggerEl) {
        const tab = new bootstrap.Tab(triggerEl);
        tab.show();
    }
}
