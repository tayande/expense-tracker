function initTheme() {
    const toggle = document.getElementById("theme-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", () => {
        const current = document.documentElement.getAttribute("data-theme");
        const next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("theme", next);
        toggle.textContent = next === "dark" ? "☀" : "☾";
    });
    const stored = localStorage.getItem("theme") || "light";
    toggle.textContent = stored === "dark" ? "☀" : "☾";
}

function initToasts() {
    document.querySelectorAll(".toast").forEach((toast) => {
        const timer = setTimeout(() => toast.remove(), 4000);
        const closeBtn = toast.querySelector(".toast-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", () => {
                clearTimeout(timer);
                toast.remove();
            });
        }
    });
}

function initDeleteModal() {
    const overlay = document.getElementById("confirm-modal");
    if (!overlay) return;
    const confirmBtn = document.getElementById("confirm-modal-confirm");
    const cancelBtn = document.getElementById("confirm-modal-cancel");
    let pendingForm = null;

    document.querySelectorAll(".delete-form").forEach((form) => {
        form.addEventListener("submit", (e) => {
            e.preventDefault();
            pendingForm = form;
            overlay.classList.add("open");
        });
    });

    cancelBtn.addEventListener("click", () => {
        pendingForm = null;
        overlay.classList.remove("open");
    });

    overlay.addEventListener("click", (e) => {
        if (e.target === overlay) {
            pendingForm = null;
            overlay.classList.remove("open");
        }
    });

    confirmBtn.addEventListener("click", () => {
        if (pendingForm) pendingForm.submit();
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initToasts();
    initDeleteModal();
});