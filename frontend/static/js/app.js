const API = "";
let allProducts = [];
let allResults = [];
let currentSort = { key: null, asc: true };
let crawlPollTimer = null;
let comparePollTimer = null;

document.addEventListener("DOMContentLoaded", () => {
    loadProducts();
    loadResults();
    loadSettings();
});

// ---- Formatting ----

function formatPrice(price) {
    if (price === null || price === undefined) return "-";
    return price.toLocaleString("de-DE", { style: "currency", currency: "EUR" });
}

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ---- Step 1: Crawl Products ----

async function loadProducts() {
    try {
        const res = await fetch(`${API}/api/products`);
        const data = await res.json();
        allProducts = data.products || [];

        const summary = document.getElementById("productSummary");
        if (allProducts.length > 0) {
            summary.classList.remove("hidden");
            document.getElementById("productCount").textContent = data.count;
            document.getElementById("crawlDate").textContent =
                `Stand: ${data.crawled_at || "-"}`;
            renderProductsList();
        }
    } catch (err) {
        console.error("Load products error:", err);
    }
}

async function startCrawl() {
    const btn = document.getElementById("crawlBtn");
    const status = document.getElementById("crawlStatus");
    btn.disabled = true;
    status.textContent = "Starte Crawl...";
    status.className = "status-text";

    try {
        const res = await fetch(`${API}/api/products/crawl`, { method: "POST" });
        const data = await res.json();

        if (!res.ok) {
            status.textContent = data.error;
            status.className = "status-text error";
            btn.disabled = false;
            return;
        }

        document.getElementById("crawlProgress").classList.remove("hidden");
        pollCrawlProgress();
    } catch (err) {
        status.textContent = "Fehler: " + err.message;
        status.className = "status-text error";
        btn.disabled = false;
    }
}

function pollCrawlProgress() {
    if (crawlPollTimer) clearInterval(crawlPollTimer);
    crawlPollTimer = setInterval(async () => {
        try {
            const res = await fetch(`${API}/api/products/crawl/status`);
            const data = await res.json();

            const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0;
            document.getElementById("crawlProgressBar").style.width = pct + "%";
            document.getElementById("crawlProgressText").textContent =
                `${data.current}/${data.total} Seiten | ${data.found} Produkte gefunden (${pct}%)`;
            document.getElementById("crawlStatus").textContent = "Crawl laeuft...";

            if (!data.running && data.current > 0) {
                clearInterval(crawlPollTimer);
                document.getElementById("crawlBtn").disabled = false;
                document.getElementById("crawlStatus").textContent = "Fertig!";
                document.getElementById("crawlProgress").classList.add("hidden");
                loadProducts();
            }
        } catch (err) {
            console.error("Poll error:", err);
        }
    }, 2000);
}

// ---- Step 2: Compare ----

async function startComparison() {
    const btn = document.getElementById("compareBtn");
    const status = document.getElementById("compareStatus");
    const offset = parseInt(document.getElementById("compareOffset").value) || 0;
    const limit = parseInt(document.getElementById("compareLimit").value) || 20;

    btn.disabled = true;
    status.textContent = "Starte Vergleich...";
    status.className = "status-text";

    try {
        const res = await fetch(`${API}/api/compare/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ offset, limit }),
        });
        const data = await res.json();

        if (!res.ok) {
            status.textContent = data.error;
            status.className = "status-text error";
            btn.disabled = false;
            return;
        }

        status.textContent = `Vergleiche ${data.count} Produkte...`;
        document.getElementById("compareProgress").classList.remove("hidden");
        pollCompareProgress();
    } catch (err) {
        status.textContent = "Fehler: " + err.message;
        status.className = "status-text error";
        btn.disabled = false;
    }
}

function pollCompareProgress() {
    if (comparePollTimer) clearInterval(comparePollTimer);
    comparePollTimer = setInterval(async () => {
        try {
            const res = await fetch(`${API}/api/compare/status`);
            const data = await res.json();

            const pct = data.total > 0 ? Math.round((data.current / data.total) * 100) : 0;
            document.getElementById("compareProgressBar").style.width = pct + "%";
            document.getElementById("compareProgressText").textContent =
                `${data.current}/${data.total} Produkte verglichen (${pct}%)`;

            // Show errors
            if (data.errors && data.errors.length > 0) {
                const errDiv = document.getElementById("compareErrors");
                errDiv.classList.remove("hidden");
                errDiv.innerHTML = data.errors.map(e =>
                    `<div>${escapeHtml(e.product)}: ${escapeHtml(e.error)}</div>`
                ).join("");
            }

            if (!data.running && data.current > 0) {
                clearInterval(comparePollTimer);
                document.getElementById("compareBtn").disabled = false;
                document.getElementById("compareStatus").textContent = "Fertig!";
                document.getElementById("compareProgress").classList.add("hidden");
                loadResults();
            }
        } catch (err) {
            console.error("Poll error:", err);
        }
    }, 3000);
}

async function compareSingleProduct(index) {
    try {
        const res = await fetch(`${API}/api/compare/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ indices: [index] }),
        });
        if (res.ok) {
            document.getElementById("compareProgress").classList.remove("hidden");
            pollCompareProgress();
        }
    } catch (err) {
        console.error("Compare single error:", err);
    }
}

// ---- Step 3: Results ----

async function loadResults() {
    try {
        const res = await fetch(`${API}/api/results`);
        allResults = await res.json();
        renderResults();
    } catch (err) {
        console.error("Load results error:", err);
    }
}

function renderResults() {
    const tbody = document.getElementById("resultsBody");
    const statsBar = document.getElementById("statsBar");

    if (allResults.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">Noch keine Vergleiche. Starte zuerst den Crawl und dann den Vergleich.</td></tr>';
        statsBar.classList.add("hidden");
        return;
    }

    // Stats
    statsBar.classList.remove("hidden");
    let cheaper = 0, expensive = 0, totalDev = 0, devCount = 0;
    allResults.forEach(r => {
        if (r.deviation_percent !== null && r.deviation_percent !== undefined) {
            if (r.deviation_percent < 0) cheaper++;
            else if (r.deviation_percent > 0) expensive++;
            totalDev += r.deviation_percent;
            devCount++;
        }
    });
    document.getElementById("statTotal").textContent = allResults.length;
    document.getElementById("statCheaper").textContent = cheaper;
    document.getElementById("statExpensive").textContent = expensive;
    document.getElementById("statAvgDev").textContent =
        devCount > 0 ? (totalDev / devCount).toFixed(1) + "%" : "-";

    // Sort
    let sorted = [...allResults];
    if (currentSort.key) {
        sorted.sort((a, b) => {
            let va = a[currentSort.key];
            let vb = b[currentSort.key];
            if (va === null || va === undefined) va = currentSort.asc ? Infinity : -Infinity;
            if (vb === null || vb === undefined) vb = currentSort.asc ? Infinity : -Infinity;
            if (typeof va === "string") return currentSort.asc ? va.localeCompare(vb) : vb.localeCompare(va);
            return currentSort.asc ? va - vb : vb - va;
        });
    }

    tbody.innerHTML = "";
    sorted.forEach(item => {
        const tr = document.createElement("tr");
        const comp = item.competitors || [];

        const devClass = item.deviation_percent !== null
            ? (item.deviation_percent < -2 ? "price-cheaper" :
               item.deviation_percent > 2 ? "price-expensive" : "price-neutral")
            : "";

        const devText = item.deviation_percent !== null
            ? (item.deviation_percent > 0 ? "+" : "") + item.deviation_percent + "%"
            : "-";

        tr.innerHTML = `
            <td>
                <a href="${escapeHtml(item.megazoo_url || '#')}" target="_blank">${escapeHtml(item.product_name)}</a>
            </td>
            <td><strong>${formatPrice(item.megazoo_price)}</strong></td>
            <td>${renderCompetitor(comp[0])}</td>
            <td>${renderCompetitor(comp[1])}</td>
            <td>${renderCompetitor(comp[2])}</td>
            <td>${formatPrice(item.avg_competitor_price)}</td>
            <td class="${devClass}">${devText}</td>
            <td>${formatPrice(item.recommended_price)}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderCompetitor(comp) {
    if (!comp) return "-";
    return `${formatPrice(comp.price)}<small>${escapeHtml(comp.source)}</small>`;
}

function sortTable(key) {
    if (currentSort.key === key) {
        currentSort.asc = !currentSort.asc;
    } else {
        currentSort.key = key;
        currentSort.asc = true;
    }
    renderResults();
}

async function clearResults() {
    if (!confirm("Alle Ergebnisse loeschen?")) return;
    await fetch(`${API}/api/results/clear`, { method: "DELETE" });
    loadResults();
}

function exportCSV() {
    window.location.href = `${API}/api/export`;
}

// ---- Products List ----

function toggleProducts() {
    const list = document.getElementById("productsList");
    const arrow = document.getElementById("productToggle");
    list.classList.toggle("hidden");
    arrow.classList.toggle("open");
}

function renderProductsList() {
    const tbody = document.getElementById("productsBody");
    const filter = (document.getElementById("productFilter")?.value || "").toLowerCase();

    const filtered = allProducts.filter(p =>
        !filter || p.name.toLowerCase().includes(filter)
    );

    tbody.innerHTML = "";
    filtered.slice(0, 200).forEach((p, idx) => {
        const realIdx = allProducts.indexOf(p);
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${realIdx}</td>
            <td><a href="${escapeHtml(p.url)}" target="_blank">${escapeHtml(p.name)}</a></td>
            <td>${formatPrice(p.price)}</td>
            <td><button class="btn-sm" onclick="compareSingleProduct(${realIdx})">Vergleichen</button></td>
        `;
        tbody.appendChild(tr);
    });

    if (filtered.length > 200) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td colspan="4" class="empty-msg">... und ${filtered.length - 200} weitere (Filter benutzen)</td>`;
        tbody.appendChild(tr);
    }
}

function filterProducts() {
    renderProductsList();
}

// ---- Settings ----

function toggleSettings() {
    const panel = document.getElementById("settingsPanel");
    const arrow = document.getElementById("settingsToggle");
    panel.classList.toggle("hidden");
    arrow.classList.toggle("open");
}

async function loadSettings() {
    try {
        const res = await fetch(`${API}/api/settings`);
        const settings = await res.json();
        if (settings.serpapi_key_masked) {
            document.getElementById("apiKey").placeholder = `Aktuell: ${settings.serpapi_key_masked}`;
        }
        if (settings.batch_size) {
            document.getElementById("batchSize").value = settings.batch_size;
            document.getElementById("compareLimit").value = settings.batch_size;
        }
    } catch (err) {
        console.error("Settings load error:", err);
    }
}

async function saveSettings() {
    const apiKey = document.getElementById("apiKey").value.trim();
    const batchSize = parseInt(document.getElementById("batchSize").value) || 20;

    const body = { batch_size: batchSize };
    if (apiKey) body.serpapi_key = apiKey;

    try {
        const res = await fetch(`${API}/api/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (res.ok) {
            if (apiKey) {
                document.getElementById("apiKey").value = "";
                document.getElementById("apiKey").placeholder =
                    `Aktuell: ${apiKey.substring(0, 4)}...${apiKey.substring(apiKey.length - 4)}`;
            }
            document.getElementById("compareLimit").value = batchSize;
            alert("Gespeichert!");
        }
    } catch (err) {
        alert("Fehler: " + err.message);
    }
}
