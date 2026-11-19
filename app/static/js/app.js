/**
 * EventSphere - Core Client Application Library
 * Handles authentication, demo account switching, toast alerts, and API client.
 */

const API_BASE = window.location.origin;

// State management
const AuthState = {
    getToken() {
        return localStorage.getItem("eventsphere_token");
    },
    getUser() {
        const u = localStorage.getItem("eventsphere_user");
        return u ? JSON.parse(u) : null;
    },
    setAuth(token, user) {
        localStorage.setItem("eventsphere_token", token);
        localStorage.setItem("eventsphere_user", JSON.stringify(user));
        this.updateUI();
    },
    logout() {
        localStorage.removeItem("eventsphere_token");
        localStorage.removeItem("eventsphere_user");
        this.updateUI();
        window.location.reload();
    },
    isLoggedIn() {
        return !!this.getToken();
    },
    getRole() {
        const user = this.getUser();
        return user ? user.role : null;
    },
    updateUI() {
        const user = this.getUser();
        const authContainer = document.getElementById("auth-header-actions");
        if (!authContainer) return;

        if (user) {
            authContainer.innerHTML = `
                <div class="dropdown">
                    <button class="btn btn-outline-primary btn-sm dropdown-toggle d-flex align-items-center gap-2" type="button" data-bs-toggle="dropdown">
                        <i class="bi bi-person-circle"></i>
                        <span>${user.name}</span>
                        <span class="badge bg-secondary">${user.role}</span>
                    </button>
                    <ul class="dropdown-menu dropdown-menu-end shadow-sm">
                        <li><h6 class="dropdown-header">${user.email}</h6></li>
                        <li><hr class="dropdown-divider"></li>
                        ${user.role === 'admin' ? '<li><a class="dropdown-item" href="/admin"><i class="bi bi-speedometer2 me-2"></i>Admin Dashboard</a></li>' : ''}
                        ${(user.role === 'staff' || user.role === 'admin') ? '<li><a class="dropdown-item" href="/scanner"><i class="bi bi-qr-code-scan me-2"></i>Gate Scanner</a></li>' : ''}
                        <li><a class="dropdown-item" href="#" onclick="AuthState.showNotificationsModal()"><i class="bi bi-bell me-2"></i>Notifications</a></li>
                        <li><hr class="dropdown-divider"></li>
                        <li><a class="dropdown-item text-danger" href="#" onclick="AuthState.logout()"><i class="bi bi-box-arrow-right me-2"></i>Sign Out</a></li>
                    </ul>
                </div>
            `;
        } else {
            authContainer.innerHTML = `
                <button class="btn btn-outline-primary btn-sm" onclick="AuthState.showLoginModal()">Sign In</button>
                <button class="btn btn-primary btn-sm" onclick="AuthState.showRegisterModal()">Register</button>
            `;
        }
    },
    async quickLogin(email, password) {
        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password })
            });
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.detail || "Authentication failed");
            }
            this.setAuth(data.access_token, {
                id: data.user_id,
                name: data.name,
                email: data.email,
                role: data.role
            });
            showToast(`Signed in as ${data.name} (${data.role})`, "success");
            const modal = bootstrap.Modal.getInstance(document.getElementById("loginModal"));
            if (modal) modal.hide();
            setTimeout(() => window.location.reload(), 400);
        } catch (err) {
            showToast(err.message, "danger");
        }
    },
    showLoginModal() {
        const el = document.getElementById("loginModal");
        if (el) new bootstrap.Modal(el).show();
    },
    showRegisterModal() {
        const el = document.getElementById("registerModal");
        if (el) new bootstrap.Modal(el).show();
    },
    async showNotificationsModal() {
        const modalEl = document.getElementById("notificationsModal");
        if (!modalEl) return;
        const listEl = document.getElementById("notifications-list");
        listEl.innerHTML = '<div class="text-center py-3"><div class="spinner-border text-primary spinner-border-sm"></div></div>';
        new bootstrap.Modal(modalEl).show();

        try {
            const res = await apiRequest("/api/auth/notifications");
            if (!res || res.length === 0) {
                listEl.innerHTML = '<p class="text-muted text-center py-3">No notifications yet.</p>';
                return;
            }
            listEl.innerHTML = res.map(n => `
                <div class="list-group-item list-group-item-action py-3 ${n.is_read ? '' : 'bg-light'}">
                    <div class="d-flex w-100 justify-content-between">
                        <h6 class="mb-1 fw-bold ${n.notification_type === 'waitlist' ? 'text-warning' : 'text-primary'}">${n.title}</h6>
                        <small class="text-muted">${new Date(n.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</small>
                    </div>
                    <p class="mb-1 text-secondary small">${n.message}</p>
                    <small class="badge bg-secondary-subtle text-secondary">${n.notification_type}</small>
                </div>
            `).join("");

            // Mark read
            apiRequest("/api/auth/notifications/read", { method: "POST" });
        } catch (e) {
            listEl.innerHTML = `<p class="text-danger small">Failed to load notifications: ${e.message}</p>`;
        }
    }
};

// Global Authenticated Fetch API Wrapper
async function apiRequest(endpoint, options = {}) {
    const headers = options.headers || {};
    const token = AuthState.getToken();
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }
    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }

    const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
    if (res.status === 401) {
        AuthState.logout();
        throw new Error("Session expired. Please sign in again.");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        let msg = data.detail;
        if (typeof msg === 'object' && msg !== null) {
            msg = msg.reason || JSON.stringify(msg);
        }
        throw new Error(msg || `Request failed with status ${res.status}`);
    }
    return data;
}

// Global Toast Alert UI
function showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.className = "toast-container position-fixed bottom-0 end-0 p-3";
        container.style.zIndex = "1090";
        document.body.appendChild(container);
    }

    const toastId = "toast-" + Date.now();
    const bgClass = type === "danger" ? "bg-danger text-white" :
                    type === "success" ? "bg-success text-white" :
                    type === "warning" ? "bg-warning text-dark" : "bg-primary text-white";

    const html = `
        <div id="${toastId}" class="toast align-items-center ${bgClass} border-0 shadow-lg" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body fw-semibold">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    container.insertAdjacentHTML("beforeend", html);
    const toastEl = document.getElementById(toastId);
    const bsToast = new bootstrap.Toast(toastEl, { delay: 4500 });
    bsToast.show();
    toastEl.addEventListener("hidden.bs.toast", () => toastEl.remove());
}

document.addEventListener("DOMContentLoaded", () => {
    AuthState.updateUI();
});
