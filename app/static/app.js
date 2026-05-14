/* ── Metrica Dashboard — frontend logic ─────────────────────────── */

let currentSection = null;
let currentFilter  = "active";
let toastTimer     = null;

// ── Initialise ──────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const firstTab = document.querySelector(".tab");
  if (firstTab) {
    currentSection = firstTab.dataset.section;
    loadSection(currentSection);
  }
  loadStats();
  loadRefreshStatus();
  loadSectionCounts();
});

// ── Section switching ───────────────────────────────────────────

function switchSection(sectionId, tabEl) {
  if (sectionId === currentSection) return;
  currentSection = sectionId;
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  tabEl.classList.add("active");
  loadSection(sectionId);
}

function setFilter(filter, pillEl) {
  currentFilter = filter;
  document.querySelectorAll(".pill").forEach(p => p.classList.remove("active"));
  pillEl.classList.add("active");
  loadSection(currentSection);
}

// ── Load listings ───────────────────────────────────────────────

async function loadSection(sectionId) {
  const container = document.getElementById("listings-container");
  const loading   = document.getElementById("loading");
  const empty     = document.getElementById("empty-state");
  const totalEl   = document.getElementById("section-total");

  container.innerHTML = "";
  loading.style.display = "flex";
  empty.style.display = "none";
  totalEl.textContent = "";

  try {
    const resp = await fetch(`/api/listings/${sectionId}?status_filter=${currentFilter}`);
    const data = await resp.json();
    loading.style.display = "none";

    if (!data.cities || data.cities.length === 0) {
      empty.style.display = "block";
      return;
    }

    totalEl.textContent = `${data.total} listings`;

    for (const group of data.cities) {
      container.appendChild(renderCityGroup(group));
    }
  } catch (err) {
    loading.style.display = "none";
    empty.style.display = "block";
    console.error("Failed to load section:", err);
  }
}

// ── Render city group ───────────────────────────────────────────

function renderCityGroup(group) {
  const section = document.createElement("section");
  section.className = "city-group";

  const header = document.createElement("div");
  header.className = "city-header";
  header.innerHTML = `
    <span class="city-name">${esc(group.city_he || group.city)}</span>
    <span class="city-count">${group.count} listings</span>
  `;
  section.appendChild(header);

  const grid = document.createElement("div");
  grid.className = "listings-grid";

  for (const listing of group.listings) {
    grid.appendChild(renderCard(listing));
  }

  section.appendChild(grid);
  return section;
}

// ── Render listing card ─────────────────────────────────────────

function renderCard(l) {
  const card = document.createElement("article");
  card.className = `listing-card status-${l.status}`;
  card.id = `card-${l.id}`;

  const badges = [];
  if (l.is_new) badges.push(`<span class="badge new">NEW</span>`);
  if (l.status === "saved") badges.push(`<span class="badge saved-badge">SAVED</span>`);

  const imgSection = l.image_url
    ? `<img src="${esc(l.image_url)}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<div class=placeholder-img>${houseSvg}</div>'">`
    : `<div class="placeholder-img">${houseSvg}</div>`;

  const specs = [];
  if (l.size_sqm)  specs.push(specTag(rulerSvg, `${l.size_sqm} sqm`));
  if (l.rooms)     specs.push(specTag(doorSvg,  `${l.rooms} rooms`));
  if (l.floor != null) specs.push(specTag(floorSvg, `Floor ${l.floor}${l.total_floors ? '/' + l.total_floors : ''}`));
  if (l.has_parking != null) specs.push(specTag(carSvg, l.has_parking ? "Parking" : "No parking"));

  const location = [l.neighborhood, l.city].filter(Boolean).join(", ");

  card.innerHTML = `
    <div class="card-image">
      ${imgSection}
      ${badges.join("")}
      <span class="source-badge">${esc(l.source)}</span>
    </div>
    <div class="card-body">
      <div class="card-price">${formatPrice(l.price)}</div>
      <div class="card-location">${esc(location)}</div>
      <div class="card-specs">${specs.join("")}</div>
    </div>
    <div class="card-actions">
      <a class="action-view" href="${esc(l.url)}" target="_blank" rel="noopener">View</a>
      <button class="action-save ${l.status === 'saved' ? 'is-saved' : ''}"
              onclick="toggleSave(${l.id}, '${l.status}')">${l.status === "saved" ? "Saved" : "Save"}</button>
      <button class="action-dismiss" onclick="dismissListing(${l.id})">Hide</button>
    </div>
  `;

  return card;
}

// ── Actions ─────────────────────────────────────────────────────

async function toggleSave(id, current) {
  const next = current === "saved" ? "new" : "saved";
  await setListingStatus(id, next);
}

async function dismissListing(id) {
  await setListingStatus(id, "not_interested");
}

async function setListingStatus(id, status) {
  try {
    await fetch(`/api/listings/${id}/status?status=${status}`, { method: "POST" });
    const card = document.getElementById(`card-${id}`);
    if (card) {
      if (currentFilter !== "all" && status === "not_interested") {
        card.style.transition = "opacity .3s, transform .3s";
        card.style.opacity = "0";
        card.style.transform = "scale(.95)";
        setTimeout(() => card.remove(), 300);
      } else {
        card.className = `listing-card status-${status}`;
        const saveBtn = card.querySelector(".action-save");
        if (saveBtn) {
          saveBtn.classList.toggle("is-saved", status === "saved");
          saveBtn.textContent = status === "saved" ? "Saved" : "Save";
          saveBtn.setAttribute("onclick", `toggleSave(${id}, '${status}')`);
        }
      }
    }
    showToast(status === "saved" ? "Listing saved" : status === "not_interested" ? "Listing hidden" : "Listing restored");
    loadStats();
    loadSectionCounts();
  } catch (err) {
    console.error("Status update failed:", err);
  }
}

// ── Refresh (re-import from JSON) ───────────────────────────────

async function triggerRefresh() {
  const btn = document.getElementById("btn-refresh");
  btn.classList.add("running");
  btn.disabled = true;
  showToast("Importing latest data…");

  try {
    const resp = await fetch("/api/refresh", { method: "POST" });
    const data = await resp.json();
    btn.classList.remove("running");
    btn.disabled = false;

    const msg = `Import complete — ${data.listings_found} found, ${data.listings_new} new`;
    showToast(msg);

    loadSection(currentSection);
    loadStats();
    loadSectionCounts();
    loadRefreshStatus();
  } catch (err) {
    btn.classList.remove("running");
    btn.disabled = false;
    showToast("Import failed");
  }
}

// ── Stats & status ──────────────────────────────────────────────

async function loadStats() {
  try {
    const resp = await fetch("/api/stats");
    const data = await resp.json();
    setText("stat-total", data.total);
    setText("stat-saved", data.saved);
  } catch (_) {}
}

async function loadRefreshStatus() {
  try {
    const resp = await fetch("/api/refresh/status");
    const data = await resp.json();
    if (data.last_scrape?.finished_at) {
      updateLastRefresh(data.last_scrape.finished_at);
    }
  } catch (_) {}
}

async function loadSectionCounts() {
  try {
    const resp = await fetch("/api/sections");
    const sections = await resp.json();
    for (const s of sections) {
      const el = document.getElementById(`tab-count-${s.id}`);
      if (el) el.textContent = s.count;
    }
  } catch (_) {}
}

function updateLastRefresh(isoDate) {
  if (!isoDate) return;
  const d = new Date(isoDate);
  const el = document.getElementById("last-refresh");
  el.textContent = `Last refresh: ${d.toLocaleDateString("en-GB")} ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
}

// ── Helpers ─────────────────────────────────────────────────────

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.querySelector(".stat-val").textContent = val ?? "—";
}

function formatPrice(p) {
  if (p == null) return "Price N/A";
  return p.toLocaleString("he-IL") + " \u20AA";
}

function esc(s) {
  if (!s) return "";
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function specTag(icon, text) {
  return `<span class="spec">${icon} ${esc(text)}</span>`;
}

function showToast(msg) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  clearTimeout(toastTimer);
  requestAnimationFrame(() => {
    toast.classList.add("show");
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3500);
  });
}

// ── Inline SVG icons ────────────────────────────────────────────

const houseSvg = `<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`;
const rulerSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.3 15.3a2.4 2.4 0 0 1 0 3.4l-2.6 2.6a2.4 2.4 0 0 1-3.4 0L2.7 8.7a2.4 2.4 0 0 1 0-3.4l2.6-2.6a2.4 2.4 0 0 1 3.4 0z"/><path d="m14.5 12.5 2-2m-5 1 2-2m-5 1 2-2"/></svg>`;
const doorSvg  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2z"/><circle cx="15.5" cy="14.5" r="1"/></svg>`;
const floorSvg = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18"/></svg>`;
const carSvg   = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 17h14v-5l-2-5H7L5 12z"/><circle cx="7.5" cy="17.5" r="1.5"/><circle cx="16.5" cy="17.5" r="1.5"/></svg>`;
