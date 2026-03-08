const API = "";

// On page load
document.addEventListener("DOMContentLoaded", () => {
    loadHistory();
    loadSettings();

    // Enter key to search
    document.getElementById("searchInput").addEventListener("keydown", (e) => {
        if (e.key === "Enter") searchProduct();
    });
});

async function searchProduct() {
    const input = document.getElementById("searchInput");
    const productName = input.value.trim();
    if (!productName) return;

    const statusEl = document.getElementById("searchStatus");
    const searchBtn = document.getElementById("searchBtn");

    statusEl.textContent = "Suche laeuft... (kann einige Sekunden dauern)";
    statusEl.className = "status-message loading";
    searchBtn.disabled = true;

    try {
        const res = await fetch(`${API}/api/search`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ product_name: productName }),
        });

        const data = await res.json();

        if (!res.ok) {
            statusEl.textContent = data.error || "Fehler bei der Suche";
            statusEl.className = "status-message error";
            return;
        }

        statusEl.textContent = `${data.total_results} Ergebnisse gefunden`;
        statusEl.className = "status-message";

        displayResults(data);
        loadHistory();
    } catch (err) {
        statusEl.textContent = "Verbindungsfehler: " + err.message;
        statusEl.className = "status-message error";
    } finally {
        searchBtn.disabled = false;
    }
}

function formatPrice(price) {
    if (price === null || price === undefined) return "-";
    return price.toLocaleString("de-DE", { style: "currency", currency: "EUR" });
}

function displayResults(data) {
    const section = document.getElementById("resultsSection");
    section.classList.remove("hidden");

    document.getElementById("resultProductName").textContent = data.product_name;

    // Megazoo price
    document.getElementById("megazooPrice").textContent = formatPrice(data.megazoo_price);
    document.getElementById("megazooSource").textContent = data.megazoo_source || "Nicht gefunden";

    // Average
    document.getElementById("avgPrice").textContent = formatPrice(data.avg_competitor_price);
    document.getElementById("competitorCount").textContent =
        `Aus ${data.competitors ? data.competitors.length : 0} Anbietern`;

    // Deviation
    const deviationEl = document.getElementById("deviation");
    const deviationCard = deviationEl.closest(".card");
    if (data.deviation_percent !== null && data.deviation_percent !== undefined) {
        const prefix = data.deviation_percent > 0 ? "+" : "";
        deviationEl.textContent = `${prefix}${data.deviation_percent}%`;
        deviationCard.className = data.deviation_percent <= 0
            ? "card deviation-card positive"
            : "card deviation-card";
        document.getElementById("deviationLabel").textContent =
            data.deviation_percent > 0 ? "Megazoo ist teurer" : "Megazoo ist guenstiger";
    } else {
        deviationEl.textContent = "-";
        document.getElementById("deviationLabel").textContent = "";
    }

    // Recommended
    document.getElementById("recommendedPrice").textContent = formatPrice(data.recommended_price);

    // Comparison table
    const tbody = document.getElementById("comparisonBody");
    tbody.innerHTML = "";

    // Add Megazoo row first
    if (data.megazoo_price) {
        const tr = document.createElement("tr");
        tr.className = "megazoo-row";
        const devFromAvg = data.avg_competitor_price
            ? ((data.megazoo_price - data.avg_competitor_price) / data.avg_competitor_price * 100).toFixed(1)
            : null;
        tr.innerHTML = `
            <td>Megazoo</td>
            <td>${formatPrice(data.megazoo_price)}</td>
            <td>${devFromAvg !== null ? (devFromAvg > 0 ? '+' : '') + devFromAvg + '%' : '-'}</td>
            <td>${data.megazoo_link ? `<a href="${escapeHtml(data.megazoo_link)}" target="_blank">Ansehen</a>` : '-'}</td>
        `;
        tbody.appendChild(tr);
    }

    // Add competitor rows
    if (data.competitors) {
        data.competitors.forEach((comp) => {
            const tr = document.createElement("tr");
            const devFromAvg = data.avg_competitor_price
                ? ((comp.price - data.avg_competitor_price) / data.avg_competitor_price * 100).toFixed(1)
                : null;
            const priceClass = data.megazoo_price
                ? (comp.price < data.megazoo_price ? "price-cheaper" : comp.price > data.megazoo_price ? "price-expensive" : "")
                : "";
            tr.innerHTML = `
                <td>${escapeHtml(comp.source)}</td>
                <td class="${priceClass}">${formatPrice(comp.price)}</td>
                <td>${devFromAvg !== null ? (devFromAvg > 0 ? '+' : '') + devFromAvg + '%' : '-'}</td>
                <td>${comp.link ? `<a href="${escapeHtml(comp.link)}" target="_blank">Ansehen</a>` : '-'}</td>
            `;
            tbody.appendChild(tr);
        });
    }
}

async function loadHistory() {
    try {
        const res = await fetch(`${API}/api/history`);
        const history = await res.json();
        displayHistory(history);
    } catch (err) {
        console.error("History load error:", err);
    }
}

function displayHistory(history) {
    const tbody = document.getElementById("historyBody");
    tbody.innerHTML = "";

    if (history.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#888;padding:2rem">Noch keine Suchen durchgefuehrt</td></tr>';
        return;
    }

    history.forEach((item) => {
        const tr = document.createElement("tr");
        const date = new Date(item.created_at).toLocaleString("de-DE", {
            day: "2-digit", month: "2-digit", year: "numeric",
            hour: "2-digit", minute: "2-digit"
        });
        const comp = item.competitors || [];

        const deviationClass = item.deviation_percent !== null
            ? (item.deviation_percent > 0 ? "price-expensive" : "price-cheaper")
            : "";

        tr.innerHTML = `
            <td>${date}</td>
            <td>${escapeHtml(item.product_name)}</td>
            <td>${formatPrice(item.megazoo_price)}</td>
            <td>${comp[0] ? formatPrice(comp[0].price) + '<br><small>' + escapeHtml(comp[0].source) + '</small>' : '-'}</td>
            <td>${comp[1] ? formatPrice(comp[1].price) + '<br><small>' + escapeHtml(comp[1].source) + '</small>' : '-'}</td>
            <td>${formatPrice(item.avg_competitor_price)}</td>
            <td class="${deviationClass}">${item.deviation_percent !== null ? (item.deviation_percent > 0 ? '+' : '') + item.deviation_percent + '%' : '-'}</td>
            <td>${formatPrice(item.recommended_price)}</td>
            <td><button class="btn-danger" onclick="deleteEntry(${item.id})">X</button></td>
        `;
        tbody.appendChild(tr);
    });
}

async function deleteEntry(id) {
    try {
        await fetch(`${API}/api/history/${id}`, { method: "DELETE" });
        loadHistory();
    } catch (err) {
        console.error("Delete error:", err);
    }
}

async function loadSettings() {
    try {
        const res = await fetch(`${API}/api/settings`);
        const settings = await res.json();
        if (settings.serpapi_key_masked) {
            document.getElementById("apiKey").placeholder = `Aktuell: ${settings.serpapi_key_masked}`;
        }
    } catch (err) {
        console.error("Settings load error:", err);
    }
}

async function saveSettings() {
    const apiKey = document.getElementById("apiKey").value.trim();
    if (!apiKey) return;

    try {
        const res = await fetch(`${API}/api/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ serpapi_key: apiKey }),
        });

        if (res.ok) {
            document.getElementById("apiKey").value = "";
            document.getElementById("apiKey").placeholder = `Aktuell: ${apiKey.substring(0, 4)}...${apiKey.substring(apiKey.length - 4)}`;
            alert("Einstellungen gespeichert!");
        }
    } catch (err) {
        alert("Fehler beim Speichern: " + err.message);
    }
}

function exportCSV() {
    window.location.href = `${API}/api/export`;
}

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
