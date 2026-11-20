/* ================================================================
   SIGN BRIDGE — JavaScript App Logic
   Handles: file upload, sample reels, API calls, job polling, 
            pipeline progress UI, dual video comparison studio
   ================================================================ */

const API_BASE = "http://localhost:5000/api";
let currentJobId = null;
let currentVideoFile = null;
let pollInterval = null;

// ─── GLOSS TICKER ANIMATION ───────────────────────────────────────────────
const glossPhrases = [
  "PILAU COOK TODAY",
  "TOMATO TWO ADD",
  "HELLO NAIROBI",
  "MUSIC LISTEN ENJOY",
  "RECIPE SHOW ME",
  "FAMILY COOK TOGETHER",
  "UGALI SUKUMA EAT",
  "FRIEND HELLO HI",
  "HARAMBEE COMMUNITY UNITY",
  "MATATU NAIROBI TRAVEL"
];
let glossIdx = 0;

function animateGlossTicker() {
  const ticker = document.getElementById("hero-gloss");
  if (!ticker) return;
  ticker.style.opacity = "0";
  setTimeout(() => {
    ticker.textContent = glossPhrases[glossIdx++ % glossPhrases.length];
    ticker.style.opacity = "1";
    ticker.style.transition = "opacity 0.4s ease";
  }, 250);
}
setInterval(animateGlossTicker, 2200);

// ─── TOAST NOTIFICATION UTILITY ───────────────────────────────────────────
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  
  const toast = document.createElement("div");
  toast.className = `toast ${type === "success" ? "toast-success" : type === "error" ? "toast-error" : ""}`;
  
  const icon = type === "success" ? "✅" : type === "error" ? "⚠️" : "ℹ️";
  toast.innerHTML = `<span style="font-size:1.1rem;">${icon}</span><span>${message}</span>`;
  
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(12px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4200);
}

// ─── SAMPLE REEL LOADER ───────────────────────────────────────────────────
function loadSampleReel(url) {
  const urlInput = document.getElementById("reel-url");
  if (urlInput) {
    urlInput.value = url;
    const clearBtn = document.getElementById("clear-url-btn");
    if (clearBtn) clearBtn.style.display = "block";
    
    // Reset any selected file so URL mode is explicit
    currentVideoFile = null;
    const zone = document.getElementById("upload-zone");
    if (zone) resetUploadZone("upload-zone");

    showToast("Sample Reel selected! Click 'Generate KSL' to begin.", "success");
    switchMode("reel");
    urlInput.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function clearUrlInput() {
  const urlInput = document.getElementById("reel-url");
  if (urlInput) urlInput.value = "";
  const clearBtn = document.getElementById("clear-url-btn");
  if (clearBtn) clearBtn.style.display = "none";
}

// Listen to URL input changes to toggle clear button
document.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("reel-url");
  const clearBtn = document.getElementById("clear-url-btn");
  if (urlInput && clearBtn) {
    urlInput.addEventListener("input", () => {
      clearBtn.style.display = urlInput.value.trim() ? "block" : "none";
    });
  }
});

// ─── MODE SWITCHING ───────────────────────────────────────────────────────
function switchMode(mode) {
  const reelPanel = document.getElementById("reel-panel");
  const creatorPanel = document.getElementById("creator-panel");
  const reelBtn = document.getElementById("reel-mode-btn");
  const creatorBtn = document.getElementById("creator-mode-btn");

  if (mode === "reel") {
    reelPanel.classList.remove("hidden");
    creatorPanel.classList.add("hidden");
    reelBtn.classList.add("active");
    creatorBtn.classList.remove("active");
    reelBtn.setAttribute("aria-selected", "true");
    creatorBtn.setAttribute("aria-selected", "false");
  } else {
    reelPanel.classList.add("hidden");
    creatorPanel.classList.remove("hidden");
    reelBtn.classList.remove("active");
    creatorBtn.classList.add("active");
    reelBtn.setAttribute("aria-selected", "false");
    creatorBtn.setAttribute("aria-selected", "true");
  }
  hideProgress();
  hideResult();
}

// ─── FILE HANDLING ────────────────────────────────────────────────────────
function handleFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;
  currentVideoFile = file;
  clearUrlInput();
  updateUploadZone(file.name, "upload-zone");
}

function handleCreatorFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  currentVideoFile = file;
  updateUploadZone(file.name, "creator-upload-zone");
}

function handleDrop(event) {
  event.preventDefault();
  const zone = document.getElementById("upload-zone");
  zone.classList.remove("drag-over");
  const file = event.dataTransfer.files[0];
  if (!file) return;
  if (!file.type.startsWith("video/")) {
    showToast("Please drop a valid MP4, MOV, or WEBM video file.", "error");
    return;
  }
  currentVideoFile = file;
  clearUrlInput();
  const fileInput = document.getElementById("video-file");
  if (fileInput) fileInput.files = event.dataTransfer.files;
  updateUploadZone(file.name, "upload-zone");
}

function handleDragOver(event) {
  event.preventDefault();
  const zone = document.getElementById("upload-zone");
  if (zone) zone.classList.add("drag-over");
}

document.addEventListener("dragleave", () => {
  const zone = document.getElementById("upload-zone");
  if (zone) zone.classList.remove("drag-over");
});

function updateUploadZone(filename, zoneId) {
  const zone = document.getElementById(zoneId);
  if (!zone) return;
  zone.onclick = null;
  zone.onkeydown = null;
  zone.innerHTML = `
    <div class="dropzone-icon-circle" style="background: rgba(16, 185, 129, 0.15); border-color: var(--accent-green); color: var(--accent-green);">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
    </div>
    <p class="dropzone-title" style="color: #34d399;">${filename}</p>
    <p class="dropzone-subtitle">Ready to process &middot; Click <strong>"Generate KSL"</strong> to begin</p>
    <button type="button" class="btn btn-sm btn-ghost" style="margin-top: 10px;"
      onclick="event.stopPropagation(); resetUploadZone('${zoneId}')">
      🔄 Choose different file
    </button>
  `;
  showToast(`Video loaded: ${filename}`, "success");
}

function resetUploadZone(zoneId) {
  currentVideoFile = null;
  const zone = document.getElementById(zoneId);
  if (!zone) return;
  if (zoneId === 'upload-zone') {
    zone.onclick = function() { document.getElementById('video-file').click(); };
    zone.onkeydown = function(e) { if(e.key === 'Enter') document.getElementById('video-file').click(); };
    zone.innerHTML = `
      <div class="dropzone-glow"></div>
      <div class="dropzone-icon-circle">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
      </div>
      <p class="dropzone-title">Drop your Reel here to upload</p>
      <p class="dropzone-subtitle">or click to browse from your device &middot; MP4, MOV, WEBM up to 200MB</p>
      <div class="dropzone-tags">
        <span class="dz-tag">MP4</span>
        <span class="dz-tag">MOV</span>
        <span class="dz-tag">WEBM</span>
        <span class="dz-tag">Max 200 MB</span>
      </div>
      <input type="file" id="video-file" accept="video/mp4,video/mov,video/quicktime,video/webm"
             class="sr-only" onchange="handleFileSelect(event)" aria-label="Select video file"/>
    `;
  } else {
    zone.onclick = function() { document.getElementById('creator-file').click(); };
    zone.innerHTML = `
      <div class="dropzone-glow"></div>
      <div class="dropzone-icon-circle">
        <span style="font-size: 2rem;">🤟</span>
      </div>
      <p class="dropzone-title">Upload your KSL signing video</p>
      <p class="dropzone-subtitle">MP4 or MOV &middot; Camera facing you clearly &middot; Good lighting</p>
      <input type="file" id="creator-file" accept="video/*" class="sr-only"
             onchange="handleCreatorFile(event)" aria-label="Select KSL video"/>
    `;
  }
}

// ─── MAIN PIPELINE (REEL → KSL) ───────────────────────────────────────────
async function processReel() {
  console.log("[SignBridge] processReel() invoked");
  const urlInput = document.getElementById("reel-url");
  const url = urlInput ? urlInput.value.trim() : "";
  const langSelect = document.getElementById("sign-language");
  const language = langSelect ? langSelect.value : "KSL";

  if (!currentVideoFile && !url) {
    showToast("Please upload a video or paste an Instagram Reel URL.", "error");
    return;
  }

  const btn = document.getElementById("process-btn");
  const btnText = document.getElementById("process-btn-text");
  if (btn) btn.disabled = true;
  if (btnText) btnText.innerHTML = `<span class="loading-spin">⏳</span> Processing...`;
  
  showProgress();
  hideResult();

  try {
    let response;

    if (currentVideoFile) {
      console.log("[SignBridge] Uploading file:", currentVideoFile.name);
      showToast(`Uploading ${currentVideoFile.name}...`, "info");
      const formData = new FormData();
      formData.append("video", currentVideoFile);
      formData.append("language", language);
      response = await fetch(`${API_BASE}/process-reel`, {
        method: "POST",
        body: formData
      });
    } else {
      console.log("[SignBridge] Processing URL:", url);
      showToast("Fetching Instagram Reel via yt-dlp...", "info");
      response = await fetch(`${API_BASE}/process-reel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_url: url, language })
      });
    }

    if (!response.ok) {
      let errMsg = "Failed to start pipeline processing";
      try {
        const err = await response.json();
        errMsg = err.error || errMsg;
      } catch (_) {}
      throw new Error(errMsg);
    }

    const data = await response.json();
    console.log("[SignBridge] Job successfully initiated:", data.job_id);
    currentJobId = data.job_id;
    startPolling(currentJobId);

  } catch (error) {
    console.error("[SignBridge] processReel error:", error);
    showError(error.message);
  }
}

// ─── CREATOR MODE (KSL → ENGLISH VOICE) ───────────────────────────────────
async function processCreator() {
  if (!currentVideoFile) {
    showToast("Please upload your KSL signing video first.", "error");
    return;
  }

  showProgress();
  hideResult();
  updateProgressUI(30, "Analyzing KSL hand and facial movements with SAM 3.1...");

  const formData = new FormData();
  formData.append("video", currentVideoFile);

  try {
    const response = await fetch(`${API_BASE}/creator-mode`, {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      let msg = "Creator mode processing failed";
      try { const d = await response.json(); msg = d.error || msg; } catch (_) {}
      throw new Error(msg);
    }

    const data = await response.json();
    updateProgressUI(100, "Complete!");

    setTimeout(() => {
      showCreatorResult(data);
    }, 500);
  } catch (error) {
    showError(error.message);
  }
}

// ─── REAL-TIME JOB POLLING ────────────────────────────────────────────────
function startPolling(jobId) {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(() => pollJob(jobId), 1500);
}

async function pollJob(jobId) {
  try {
    const response = await fetch(`${API_BASE}/status/${jobId}`);
    if (!response.ok) return;

    const data = await response.json();
    updateProgressUI(data.progress, data.step);
    updatePipelineStages(data.progress);

    if (data.status === "done") {
      clearInterval(pollInterval);
      showToast("KSL Video generated successfully!", "success");
      setTimeout(() => showResult(data), 450);

      const btn = document.getElementById("process-btn");
      if (btn) btn.disabled = false;
      const btnText = document.getElementById("process-btn-text");
      if (btnText) btnText.textContent = "Generate KSL";
    }

    if (data.status === "error") {
      clearInterval(pollInterval);
      showError(data.error);
      const btn = document.getElementById("process-btn");
      if (btn) btn.disabled = false;
      const btnText = document.getElementById("process-btn-text");
      if (btnText) btnText.textContent = "Generate KSL";
    }
  } catch (e) {
    console.error("Polling error:", e);
  }
}

// ─── PROGRESS UI UPDATES ──────────────────────────────────────────────────
function showProgress() {
  const sec = document.getElementById("progress-section");
  if (sec) sec.classList.remove("hidden");
  resetPipelineStages();
  sec.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideProgress() {
  const sec = document.getElementById("progress-section");
  if (sec) sec.classList.add("hidden");
}

function updateProgressUI(pct, step) {
  const fill = document.getElementById("progress-fill");
  const pctEl = document.getElementById("progress-pct");
  const stepEl = document.getElementById("progress-step");

  if (fill) fill.style.width = `${pct}%`;
  if (pctEl) pctEl.textContent = `${pct}%`;
  if (stepEl) stepEl.textContent = step;

  const track = document.querySelector(".progress-track");
  if (track) track.setAttribute("aria-valuenow", pct);
}

function resetPipelineStages() {
  ["wonder", "spark", "sam", "image"].forEach(s => {
    const el = document.getElementById(`stage-${s}`);
    if (el) el.className = "prog-stage";
  });
}

function updatePipelineStages(pct) {
  const stages = [
    { id: "stage-wonder", threshold: 25 },
    { id: "stage-spark",  threshold: 50 },
    { id: "stage-sam",    threshold: 65 },
    { id: "stage-image",  threshold: 85 }
  ];

  stages.forEach((stage, idx) => {
    const el = document.getElementById(stage.id);
    if (!el) return;
    if (pct >= stage.threshold) {
      el.className = "prog-stage done";
    } else if (pct >= (stages[idx - 1]?.threshold ?? 0)) {
      el.className = "prog-stage active";
    } else {
      el.className = "prog-stage";
    }
  });
}

// ─── RESULT STUDIO PRESENTATION ───────────────────────────────────────────
function formatGlossChips(glossText) {
  if (!glossText) return "NO GLOSS GENERATED";
  const phrases = glossText.split("|");
  return phrases.map(p => {
    const tokens = p.trim().split(/\s+/).filter(Boolean);
    const chips = tokens.map(t => `<span class="gloss-chip">${t}</span>`).join(" ");
    return `<span class="gloss-phrase">${chips}</span>`;
  }).join('<span class="gloss-separator"> &bull; </span>');
}

function showResult(data) {
  hideProgress();
  const section = document.getElementById("result-section");
  if (!section) return;
  section.classList.remove("hidden");

  // Show original video
  const origVideo = document.getElementById("original-video");
  if (origVideo) {
    if (currentVideoFile) {
      origVideo.src = URL.createObjectURL(currentVideoFile);
    } else if (data.input_path) {
      origVideo.src = `${API_BASE.replace("/api", "")}/${data.input_path}`;
    }
  }

  // Show output video
  const outVideo = document.getElementById("output-video");
  if (outVideo && data.download_url) {
    outVideo.src = `${API_BASE.replace("/api", "")}${data.download_url}`;
    const dlBtn = document.getElementById("download-btn");
    if (dlBtn) dlBtn.dataset.url = data.download_url;
  }

  // Show formatted KSL Gloss
  const glossEl = document.getElementById("gloss-output");
  if (glossEl) {
    if (data.ksl_gloss) {
      glossEl.innerHTML = formatGlossChips(data.ksl_gloss);
    } else {
      glossEl.textContent = "No gloss tokens generated";
    }
  }

  // Show rich telemetry metadata chips
  const metaEl = document.getElementById("result-meta");
  if (metaEl) {
    const cornerFormatted = (data.avatar_corner || "bottom_right").replace("_", " ").toUpperCase();
    metaEl.innerHTML = `
      <span style="display:inline-flex;gap:12px;flex-wrap:wrap;align-items:center;">
        <span>🎯 Corner: <strong>${cornerFormatted}</strong></span>
        <span>🇰🇪 Language: <strong>${data.language || "KSL"}</strong></span>
        <span>⚡ Job: <code>${data.job_id}</code></span>
        <span style="color:#34d399;">✓ Meta Multi-Model Verified</span>
      </span>
    `;
  }

  section.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showCreatorResult(data) {
  hideProgress();
  const section = document.getElementById("result-section");
  if (!section) return;
  section.classList.remove("hidden");

  const titleEl = document.getElementById("result-title");
  if (titleEl) titleEl.textContent = "English Voice + Captions Ready";

  const glossEl = document.getElementById("gloss-output");
  if (glossEl) {
    const signs = data.ksl_glosses?.join(" ") || "SIGNS DETECTED";
    glossEl.innerHTML = `
      <div><strong>Detected KSL Signs:</strong> ${formatGlossChips(signs)}</div>
      <div style="margin-top:10px;color:#f8fafc;"><strong>Synthesized English Voiceover:</strong> &ldquo;${data.english_text || ""}&rdquo;</div>
    `;
  }

  const dlBtn = document.getElementById("download-btn");
  if (data.download_url && dlBtn) dlBtn.dataset.url = data.download_url;

  section.scrollIntoView({ behavior: "smooth", block: "start" });
}

function hideResult() {
  const section = document.getElementById("result-section");
  if (section) section.classList.add("hidden");
  
  const btn = document.getElementById("process-btn");
  if (btn) {
    btn.disabled = false;
    const btnText = document.getElementById("process-btn-text");
    if (btnText) btnText.textContent = "Generate KSL";
  }
}

function resetAndHide() {
  hideResult();
  const origVideo = document.getElementById("original-video");
  const outVideo = document.getElementById("output-video");
  if (origVideo) origVideo.pause();
  if (outVideo) outVideo.pause();
  
  const demoSection = document.getElementById("demo");
  if (demoSection) demoSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showError(message) {
  hideProgress();
  showToast(message, "error");
  
  const btn = document.getElementById("process-btn");
  if (btn) {
    btn.disabled = false;
    const btnText = document.getElementById("process-btn-text");
    if (btnText) btnText.textContent = "Generate KSL";
  }
}

// ─── DUAL VIDEO PLAYBACK CONTROLLER ───────────────────────────────────────
function playBothVideos() {
  const v1 = document.getElementById("original-video");
  const v2 = document.getElementById("output-video");
  if (v1 && v2) {
    if (v1.paused || v2.paused) {
      v1.play().catch(e => console.log("v1 play error", e));
      v2.play().catch(e => console.log("v2 play error", e));
      showToast("Playing both videos synchronized", "info");
    } else {
      v1.pause();
      v2.pause();
    }
  } else {
    showToast("Videos not ready for playback yet", "info");
  }
}

// ─── RESULT DOWNLOAD ACTION ───────────────────────────────────────────────
function downloadResult() {
  const btn = document.getElementById("download-btn");
  const url = btn ? btn.dataset.url : null;
  if (!url) {
    showToast("Download URL is not ready yet", "error");
    return;
  }

  const link = document.createElement("a");
  link.href = `${API_BASE.replace("/api", "")}${url}`;
  link.download = "sign_bridge_ksl_reel.mp4";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast("Downloading accessible KSL Reel...", "success");
}

// ─── SMOOTH SCROLL FOR IN-PAGE NAV ────────────────────────────────────────
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener("click", function(e) {
    const targetId = this.getAttribute("href");
    if (targetId && targetId !== "#") {
      e.preventDefault();
      const target = document.querySelector(targetId);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  });
});

console.log(`
╔═══════════════════════════════════════════════════════╗
║          SIGN BRIDGE — KSL AI STUDIO v1.2.0           ║
║  Multimodal Sign Language Overlay for Instagram Reels ║
║  Built for Meta Global AI Hackathon 2026              ║
╚═══════════════════════════════════════════════════════╝
`);
