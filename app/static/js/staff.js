/**
 * EventSphere - Gate Staff Scanner Controller
 * Phone Camera QR Scanner, Manual Fallback, Audio/Visual Feedback, and Fraud Detection
 */

let html5QrCode = null;
let isScanning = false;
let gateEventId = null;

// Audio Synthesizer Feedback (Web Audio API)
const AudioFeedback = {
    ctx: null,
    init() {
        if (!this.ctx) {
            this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        }
    },
    playAdmit() {
        this.init();
        if (!this.ctx) return;
        const now = this.ctx.currentTime;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(523.25, now); // C5
        osc.frequency.exponentialRampToValueAtTime(783.99, now + 0.15); // G5
        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(now);
        osc.stop(now + 0.25);
    },
    playReject() {
        this.init();
        if (!this.ctx) return;
        const now = this.ctx.currentTime;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = "sawtooth";
        osc.frequency.setValueAtTime(220, now); // A3
        osc.frequency.setValueAtTime(160, now + 0.1);
        gain.gain.setValueAtTime(0.4, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.35);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(now);
        osc.stop(now + 0.35);
    }
};

document.addEventListener("DOMContentLoaded", () => {
    loadGateEvents();
    loadScanLogs();
    setupManualEntry();
});

async function loadGateEvents() {
    try {
        const events = await apiRequest("/api/events?status_filter=all");
        const select = document.getElementById("gate-event-select");
        if (select) {
            select.innerHTML = '<option value="">All Events (Accept any valid ticket)</option>' +
                events.map(e => `<option value="${e.id}">${e.title} (${e.venue_name || 'Venue'})</option>`).join("");
            select.addEventListener("change", (e) => {
                gateEventId = e.target.value ? parseInt(e.target.value) : null;
            });
        }
    } catch (e) {}
}

function startCameraScanner() {
    const readerDiv = document.getElementById("reader");
    const btnStart = document.getElementById("btn-start-camera");
    const btnStop = document.getElementById("btn-stop-camera");

    if (typeof Html5Qrcode === "undefined") {
        showToast("HTML5 QR Scanner library loading...", "warning");
        return;
    }

    html5QrCode = new Html5Qrcode("reader");
    const config = { fps: 10, qrbox: { width: 250, height: 250 } };

    html5QrCode.start(
        { facingMode: "environment" }, // Prefer rear camera on mobile phones
        config,
        onQrCodeSuccess,
        onQrCodeError
    ).then(() => {
        isScanning = true;
        btnStart.classList.add("d-none");
        btnStop.classList.remove("d-none");
        showToast("Camera active. Point at ticket QR code.", "info");
    }).catch(err => {
        showToast("Camera permission denied or camera not found: " + err, "danger");
    });
}

function stopCameraScanner() {
    if (html5QrCode && isScanning) {
        html5QrCode.stop().then(() => {
            isScanning = false;
            document.getElementById("btn-start-camera").classList.remove("d-none");
            document.getElementById("btn-stop-camera").classList.add("d-none");
        });
    }
}

let lastScannedCode = null;
let lastScanTime = 0;

function onQrCodeSuccess(decodedText) {
    const now = Date.now();
    // Debounce duplicate reads within 3 seconds
    if (decodedText === lastScannedCode && (now - lastScanTime) < 3000) {
        return;
    }
    lastScannedCode = decodedText;
    lastScanTime = now;
    processTicketVerification(decodedText);
}

function onQrCodeError(errorMessage) {
    // Ignore frame parsing errors
}

function setupManualEntry() {
    const form = document.getElementById("manual-scan-form");
    if (form) {
        form.addEventListener("submit", (e) => {
            e.preventDefault();
            const input = document.getElementById("manual-code-input");
            const code = input.value.trim();
            if (code) {
                processTicketVerification(code);
                input.value = "";
            }
        });
    }
}

async function processTicketVerification(code) {
    const feedbackBox = document.getElementById("scan-feedback-container");
    feedbackBox.innerHTML = '<div class="alert alert-info py-3 text-center"><div class="spinner-border spinner-border-sm me-2"></div>Verifying with TicketAgent...</div>';

    try {
        const payload = { ticket_code: code };
        if (gateEventId) payload.event_id = gateEventId;

        const res = await apiRequest("/api/tickets/scan", {
            method: "POST",
            body: JSON.stringify(payload)
        });

        renderScanFeedback(res);
        loadScanLogs();
    } catch (err) {
        AudioFeedback.playReject();
        feedbackBox.innerHTML = `
            <div class="scan-feedback-banner scan-reject text-center">
                <i class="bi bi-x-circle-fill fs-1 d-block mb-2"></i>
                <h4 class="mb-1">Access Denied</h4>
                <p class="mb-0">${err.message}</p>
            </div>
        `;
    }
}

function renderScanFeedback(data) {
    const container = document.getElementById("scan-feedback-container");

    if (data.success && data.result === "admit") {
        AudioFeedback.playAdmit();
        container.innerHTML = `
            <div class="scan-feedback-banner scan-admit text-center shadow">
                <i class="bi bi-check-circle-fill fs-1 d-block mb-1 text-success"></i>
                <h3 class="fw-bold mb-1">ADMIT PASSENGER</h3>
                <h5 class="fw-bold text-dark">${data.attendee_name || 'Attendee'}</h5>
                <p class="mb-1"><strong>Event:</strong> ${data.event_title}</p>
                <p class="mb-1"><strong>Category:</strong> ${data.category_name} • <code>${data.ticket_code}</code></p>
                <small class="text-success fw-bold">Verified by TicketAgent</small>
            </div>
        `;
    } else {
        AudioFeedback.playReject();
        const isSuspicious = data.is_suspicious;
        const bannerClass = isSuspicious ? "scan-reject border-danger" : "scan-warning";

        container.innerHTML = `
            <div class="scan-feedback-banner ${bannerClass} text-center shadow">
                <i class="bi ${isSuspicious ? 'bi-shield-fill-x text-danger' : 'bi-exclamation-triangle-fill text-warning'} fs-1 d-block mb-1"></i>
                <h3 class="fw-bold mb-1 text-uppercase">${data.result.replace('_', ' ')}</h3>
                <h5 class="fw-bold mb-1">${data.message}</h5>
                ${data.attendee_name ? `<p class="mb-1"><strong>Registered to:</strong> ${data.attendee_name}</p>` : ''}
                <p class="mb-1"><strong>Code:</strong> <code>${data.ticket_code}</code></p>
                ${isSuspicious ? `
                    <div class="badge bg-danger p-2 fs-6 mt-2 d-inline-block">
                        <i class="bi bi-camera-fill me-1"></i>SUSPICIOUS REPEATED SCAN: Possible Shared Screenshot!
                    </div>
                ` : ''}
            </div>
        `;
    }
}

async function loadScanLogs() {
    const tableBody = document.getElementById("scan-logs-tbody");
    if (!tableBody) return;

    try {
        const logs = await apiRequest("/api/tickets/scan-logs?limit=15");
        if (!logs || logs.length === 0) {
            tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No scan attempts logged today.</td></tr>';
            return;
        }

        tableBody.innerHTML = logs.map(l => {
            const isAdmit = l.result === "admit";
            const badgeClass = isAdmit ? "bg-success" : l.is_suspicious ? "bg-danger" : "bg-warning text-dark";
            return `
                <tr>
                    <td class="small font-monospace">${new Date(l.scan_time).toLocaleTimeString()}</td>
                    <td class="small font-monospace fw-bold">${l.ticket_code}</td>
                    <td><span class="badge ${badgeClass}">${l.result.toUpperCase()}</span></td>
                    <td class="small text-muted">${l.reason || ''}</td>
                </tr>
            `;
        }).join("");
    } catch (e) {}
}
