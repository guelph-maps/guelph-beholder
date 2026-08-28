"use strict";

// The map renders MISSING points only. It follows the table's civic/unit
// filter, which starts on civic: Guelph's ~6.8k unmapped units would otherwise
// bury the civic residue the 2025 import left behind.

let selectedId = null;
let selectedLat = null;
let selectedLon = null;

// Mirrors the #kind-filter select; "" means civic + unit.
let kindFilter = "civic";

function kindExpr() {
  return kindFilter ? ["==", ["get", "kind"], kindFilter] : ["has", "kind"];
}

function osmUrl(lat, lon) {
  return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=19/${lat}/${lon}`;
}

const map = new maplibregl.Map({
  container: "map",
  style: "https://tiles.openfreemap.org/styles/positron",
  center: [-80.248, 43.545],
  zoom: 12,
});
map.addControl(new maplibregl.NavigationControl(), "top-right");

map.on("load", () => {
  // The missing set is small (hundreds), so render every point individually
  // rather than clustering.
  map.addSource("points", { type: "geojson", data: "/api/points.geojson" });

  map.addLayer({
    id: "pts", type: "circle", source: "points",
    filter: kindExpr(),
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 3, 16, 7],
      "circle-color": "#d32f2f",
      "circle-stroke-width": 0.75,
      "circle-stroke-color": "rgba(0,0,0,0.4)",
    },
  });

  map.addLayer({
    id: "pts-sel", type: "circle", source: "points",
    filter: ["==", ["get", "id"], -1],
    paint: {
      "circle-radius": 9, "circle-color": "#1565c0",
      "circle-stroke-width": 2, "circle-stroke-color": "#fff",
    },
  });

  // Click a missing point.
  map.on("click", "pts", (e) => {
    const f = e.features[0];
    const [lon, lat] = f.geometry.coordinates;
    select(f.properties.id, lon, lat, { fly: false });
    highlightRow(f.properties.id);
    loadDetail(f.properties.id);
  });

  map.on("mouseenter", "pts", () => { map.getCanvas().style.cursor = "pointer"; });
  map.on("mouseleave", "pts", () => { map.getCanvas().style.cursor = ""; });
});

function select(id, lon, lat, opts = {}) {
  selectedId = id;
  selectedLat = lat;
  selectedLon = lon;
  if (map.getLayer("pts-sel")) {
    map.setFilter("pts-sel", ["==", ["get", "id"], id]);
  }
  if (opts.fly && lon != null && lat != null) {
    map.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), 17) });
  }
}

function highlightRow(id) {
  document.querySelectorAll("#table-body tr.selected")
    .forEach((tr) => tr.classList.remove("selected"));
  const tr = document.querySelector(`#table-body tr[data-id="${id}"]`);
  if (tr) {
    tr.classList.add("selected");
    tr.scrollIntoView({ block: "nearest" });
  }
}

function loadDetail(id) {
  if (window.htmx) {
    htmx.ajax("GET", `/address/${id}`, { target: "#detail", swap: "innerHTML" })
      .then(() => document.getElementById("detail").classList.remove("hidden"))
      .catch(() => {});
  }
}

// Table row click (delegated; rows are swapped in by HTMX).
document.addEventListener("click", (e) => {
  const tr = e.target.closest("#table-body tr.row");
  if (!tr) return;
  const id = Number(tr.dataset.id);
  select(id, Number(tr.dataset.lon), Number(tr.dataset.lat), { fly: true });
  highlightRow(id);
  loadDetail(id);
});

// "O" opens the selected address on OpenStreetMap in a new tab.
document.addEventListener("keydown", (e) => {
  if (e.key !== "o" && e.key !== "O") return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
  if (selectedLat == null || selectedLon == null) return;
  e.preventDefault();
  window.open(osmUrl(selectedLat, selectedLon), "_blank", "noopener");
});

// Keep the map's civic/unit filter in step with the table's.
document.addEventListener("change", (e) => {
  if (!e.target || e.target.id !== "kind-filter") return;
  kindFilter = e.target.value;
  if (map.getLayer("pts")) map.setFilter("pts", kindExpr());
  const legend = document.getElementById("legend-kind");
  if (legend) {
    legend.textContent = kindFilter === "civic" ? "civic addresses only"
      : kindFilter === "unit" ? "unit addresses only"
      : "civic + unit addresses";
  }
});

window.beholderRefreshPoints = () => {
  const src = map.getSource("points");
  if (src) src.setData("/api/points.geojson");
};
