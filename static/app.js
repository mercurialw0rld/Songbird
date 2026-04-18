const $ = (sel) => document.querySelector(sel);

const LS_GOOGLE = "songbird_google_api_key";
const LS_COHERE = "songbird_cohere_api_key";

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function renderReply(text) {
  const el = $("#reply");
  el.innerHTML = escapeHtml(text || "");
}

function loadKeysFromStorage() {
  const g = localStorage.getItem(LS_GOOGLE);
  const c = localStorage.getItem(LS_COHERE);
  if (g) $("#key-google").value = g;
  if (c) $("#key-cohere").value = c;
}

function saveKeysToStorage() {
  const g = $("#key-google").value.trim();
  const c = $("#key-cohere").value.trim();
  if (g) localStorage.setItem(LS_GOOGLE, g);
  else localStorage.removeItem(LS_GOOGLE);
  if (c) localStorage.setItem(LS_COHERE, c);
  else localStorage.removeItem(LS_COHERE);
  const badge = $("#keys-saved");
  badge.hidden = false;
  setTimeout(() => {
    badge.hidden = true;
  }, 2200);
}

function formatHttpError(data, status) {
  const d = data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  return `Error ${status}`;
}

function renderTracks(tracks) {
  const wrap = $("#tracks");
  const tpl = $("#tpl-track");
  wrap.innerHTML = "";
  if (!tracks || !tracks.length) return;

  for (const t of tracks) {
    const node = tpl.content.cloneNode(true);
    node.querySelector(".track-title").textContent = t.track_name || "—";
    node.querySelector(".track-artist").textContent = t.track_artist || "";
    const g = [t.playlist_genre, t.playlist_subgenre].filter(Boolean).join(" · ");
    node.querySelector(".track-genre").textContent = g || "♪";
    const a = node.querySelector(".track-link");
    if (t.spotify_url) {
      a.href = t.spotify_url;
    } else {
      a.removeAttribute("href");
      a.classList.add("is-disabled");
      a.textContent = "No Spotify link";
      a.style.pointerEvents = "none";
      a.style.opacity = "0.45";
    }
    wrap.appendChild(node);
  }
}

async function submit() {
  const q = $("#q").value.trim();
  const btn = $("#btn");
  const err = $("#err");
  const tracksSec = $("#tracks-section");
  const replySec = $("#reply-section");

  err.hidden = true;
  err.textContent = "";

  if (!q) {
    err.textContent = "Type something to search.";
    err.hidden = false;
    return;
  }

  btn.disabled = true;
  btn.querySelector(".btn-text").textContent = "Tuning in…";

  tracksSec.hidden = true;
  replySec.hidden = true;
  $("#tracks").innerHTML = "";
  $("#reply").textContent = "";

  try {
    const google_api_key = $("#key-google").value.trim() || null;
    const cohere_api_key = $("#key-cohere").value.trim() || null;

    const res = await fetch("/api/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: q,
        google_api_key,
        cohere_api_key,
      }),
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(formatHttpError(data, res.status));
    }
    renderReply(data.reply);
    renderTracks(data.tracks || []);

    replySec.hidden = false;
    if (data.tracks && data.tracks.length) tracksSec.hidden = false;
  } catch (e) {
    err.textContent = e.message || "Something went wrong. Is the server running?";
    err.hidden = false;
    replySec.hidden = false;
    renderReply("");
  } finally {
    btn.disabled = false;
    btn.querySelector(".btn-text").textContent = "Beam to the cosmos";
  }
}

loadKeysFromStorage();

$("#btn-save-keys").addEventListener("click", saveKeysToStorage);

$("#btn").addEventListener("click", submit);
$("#q").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
    ev.preventDefault();
    submit();
  }
});
