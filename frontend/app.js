/* ================================================================
   SIGN BRIDGE — JavaScript App Logic
   Handles: file upload, API calls, job polling, progress UI
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
  "FRIEND HELLO HI"
];
let glossIdx = 0;
function animateGlossTicker() {
  const ticker = document.getElementById("hero-gloss");
  if (!ticker) return;
  ticker.style.opacity = 0;
  setTimeout(() => {
    ticker.textContent = glossPhrases[glossIdx++ % glossPhrases.length];
    ticker.style.opacity = 1;
    ticker.style.transition = "opacity 0.5s";
  }, 300);
}
setInterval(animateGlossTicker, 2200);

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
    alert("Please drop a video file.");
    return;
  }
  currentVideoFile = file;
  document.getElementById("video-file").files = event.dataTransfer.files;
  updateUploadZone(file.name, "upload-zone");
}

function handleDragOver(event) {
  event.preventDefault();
  document.getElementById("upload-zone").classList.add("drag-over");
}

document.addEventListener("dragleave", () => {
  const zone = document.getElementById("upload-zone");
  if (zone) zone.classList.remove("drag-over");
});

function updateUploadZone(filename, zoneId) {
  const zone = document.getElementById(zoneId);
  // Remove the onclick so clicking the "ready" zone doesn't re-open the picker
  zone.onclick = null;
  zone.onkeydown = null;
  zone.innerHTML = `
    <div class="upload-icon">&#x2705;</div>
    <p class="upload-title">${filename}</p>
    <p class="upload-sub">Ready to process &mdash; click <strong>"Generate KSL"</strong> to begin</p>
    <button class="btn btn-ghost" style="margin-top:10px;font-size:0.8rem;"
      onclick="resetUploadZone('${zoneId}')">&#x1F504; Choose different file</button>
  `;
}

function resetUploadZone(zoneId) {
  currentVideoFile = null;
  const zone = document.getElementById(zoneId);
  if (zoneId === 'upload-zone') {
    zone.onclick = function() { document.getElementById('video-file').click(); };
    zone.onkeydown = function(e) { if(e.key==='Enter') document.getElementById('video-file').click(); };
    zone.innerHTML = `
      <div class="upload-icon">&#x1F3AC;</div>
      <p class="upload-title">Drop your Reel here</p>
      <p class="upload-sub">or paste an Instagram URL below &middot; MP4, MOV up to 200MB</p>
      <input type="file" id="video-file" accept="video/mp4,video/mov,video/quicktime"
             class="sr-only" onchange="handleFileSelect(event)" aria-label="Select video file"/>
    `;
  } else {
    zone.onclick = function() { document.getElementById('creator-file').click(); };
    zone.innerHTML = `
      <div class="upload-icon">&#x1F91F;</div>
      <p class="upload-title">Upload your KSL signing video</p>
      <p class="upload-sub">We'll add English voice + captions for hearing audiences</p>
      <input type="file" id="creator-file" accept="video/*" class="sr-only"
             onchange="handleCreatorFile(event)" aria-label="Select KSL video"/>
    `;
  }
}

// ─── MAIN PIPELINE ────────────────────────────────────────────────────────
async function processReel() {
  console.log("[SignBridge] processReel() called");
  const urlInput = document.getElementById("reel-url");
  const url = urlInput ? urlInput.value.trim() : "";
  const langSelect = document.getElementById("sign-language");
  const language = langSelect ? langSelect.value : "KSL";

  if (!currentVideoFile && !url) {
    alert("Please upload a video or paste an Instagram Reel URL.");
    return;
  }

  const btn = document.getElementById("process-btn");
  const btnText = document.getElementById("process-btn-text");
  if (btn) btn.disabled = true;
  if (btnText) btnText.textContent = "Processing...";
  showProgress();
  resetAndHide();    // reset result-section to clean state, then hide

  try {
    let response;

    if (currentVideoFile) {
      console.log("[SignBridge] Uploading file:", currentVideoFile.name);
      const formData = new FormData();
      formData.append("video", currentVideoFile);
      formData.append("language", language);
      response = await fetch(`${API_BASE}/process-reel`, {
        method: "POST",
        body: formData
      });
    } else {
      console.log("[SignBridge] Processing URL:", url);
      response = await fetch(`${API_BASE}/process-reel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_url: url, language })
      });
    }

    if (!response.ok) {
      let errMsg = "Failed to start processing";
      try { const err = await response.json(); errMsg = err.error || errMsg; } catch (_) {}
      throw new Error(errMsg);
    }

    const data = await response.json();
    console.log("[SignBridge] Job started:", data.job_id);
    currentJobId = data.job_id;
    startPolling(currentJobId);

  } catch (error) {
    console.error("[SignBridge] processReel error:", error);
    showError(error.message);
  }
}

async function processCreator() {
  if (!currentVideoFile) {
    alert("Please upload your KSL signing video.");
    return;
  }

  showProgress();
  hideResult();
  updateProgressUI(30, "Analyzing KSL signs with SAM 3.1...");

  const formData = new FormData();
  formData.append("video", currentVideoFile);

  try {
    const response = await fetch(`${API_BASE}/creator-mode`, {
      method: "POST",
      body: formData
    });

    if (!response.ok) throw new Error("Creator mode processing failed");

    const data = await response.json();
    updateProgressUI(100, "Complete!");

    setTimeout(() => {
      showCreatorResult(data);
    }, 500);
  } catch (error) {
    showError(error.message);
  }
}

// ─── JOB POLLING ─────────────────────────────────────────────────────────
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
      setTimeout(() => showResult(data), 400);

      // Re-enable button
      const btn = document.getElementById("process-btn");
      btn.disabled = false;
      document.getElementById("process-btn-text").textContent = "Generate KSL";
    }

    if (data.status === "error") {
      clearInterval(pollInterval);
      showError(data.error);
      const btn = document.getElementById("process-btn");
      btn.disabled = false;
      document.getElementById("process-btn-text").textContent = "Generate KSL";
    }
  } catch (e) {
    console.error("Polling error:", e);
  }
}

// ─── PROGRESS UI ──────────────────────────────────────────────────────────
function showProgress() {
  document.getElementById("progress-section").classList.remove("hidden");
  resetPipelineStages();
}

function hideProgress() {
  document.getElementById("progress-section").classList.add("hidden");
}

function updateProgressUI(pct, step) {
  document.getElementById("progress-fill").style.width = `${pct}%`;
  document.getElementById("progress-pct").textContent = `${pct}%`;
  document.getElementById("progress-step").textContent = step;

  const progressBar = document.querySelector(".progress-bar");
  if (progressBar) progressBar.setAttribute("aria-valuenow", pct);
}

function resetPipelineStages() {
  ["wonder", "spark", "sam", "image"].forEach(s => {
    const el = document.getElementById(`stage-${s}`);
    if (el) el.className = "stage";
  });
}

function updatePipelineStages(pct) {
  const stages = [
    { id: "stage-wonder", threshold: 25 },  // backend: 5→25
    { id: "stage-spark",  threshold: 50 },  // backend: 25→50
    { id: "stage-sam",    threshold: 65 },  // backend: 50→65
    { id: "stage-image",  threshold: 85 }   // backend: 65→85 (not 90)
  ];

  stages.forEach((stage, idx) => {
    const el = document.getElementById(stage.id);
    if (!el) return;
    if (pct >= stage.threshold) {
      el.className = "stage done";
    } else if (pct >= (stages[idx - 1]?.threshold ?? 0)) {
      el.className = "stage active";
    } else {
      el.className = "stage";
    }
  });
}

// ─── RESULT UI ────────────────────────────────────────────────────────────
function showResult(data) {
  hideProgress();
  const section = document.getElementById("result-section");
  section.classList.remove("hidden");

  // Show original video
  if (currentVideoFile) {
    const origVideo = document.getElementById("original-video");
    origVideo.src = URL.createObjectURL(currentVideoFile);
  }

  // Show output video
  if (data.download_url) {
    const outVideo = document.getElementById("output-video");
    outVideo.src = `${API_BASE.replace("/api", "")}${data.download_url}`;
    document.getElementById("download-btn").dataset.url = data.download_url;
  }

  // Show KSL gloss
  const glossEl = document.getElementById("gloss-output");
  if (data.ksl_gloss) {
    glossEl.textContent = data.ksl_gloss;
  }

  // Show metadata
  const metaEl = document.getElementById("result-meta");
  metaEl.innerHTML = `
    Avatar placed in: <strong>${data.avatar_corner || "bottom-right"}</strong> &nbsp;|&nbsp;
    Language: <strong>${data.language || "KSL"}</strong> &nbsp;|&nbsp;
    Job ID: <code>${data.job_id}</code>
  `;

  section.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showCreatorResult(data) {
  hideProgress();
  const section = document.getElementById("result-section");
  if (!section) return;
  section.classList.remove("hidden");

  const titleEl = section.querySelector(".result-title");
  if (titleEl) titleEl.textContent = "English Voice + Captions Ready";

  const glossEl = document.getElementById("gloss-output");
  if (glossEl) glossEl.textContent =
    `KSL: ${data.ksl_glosses?.join(" ") || ""}\n-> English: ${data.english_text || ""}`;

  const dlBtn = document.getElementById("download-btn");
  if (data.download_url && dlBtn) dlBtn.dataset.url = data.download_url;

  section.scrollIntoView({ behavior: "smooth", block: "start" });
}

function hideResult() {
  const section = document.getElementById("result-section");
  if (!section) return;
  section.classList.add("hidden");
  // result-title may not have an id — use class selector
  const title = section.querySelector(".result-title");
  if (title) title.textContent = "KSL Video Ready";
  const btn = document.getElementById("process-btn");
  if (btn) {
    btn.disabled = false;
    const btnText = document.getElementById("process-btn-text");
    if (btnText) btnText.textContent = "Generate KSL";
  }
}

function resetAndHide() {
  // Fully restore result-section to its original HTML, then hide it
  const section = document.getElementById("result-section");
  if (!section) return;
  section.innerHTML = `
    <h3 class="result-title">KSL Video Ready</h3>
    <div class="result-split">
      <div class="result-panel">
        <div class="result-panel-label">Original Reel</div>
        <video id="original-video" class="result-video" controls aria-label="Original Reel">
          <track kind="captions" label="English"/>
        </video>
      </div>
      <div class="result-arrow" aria-hidden="true">&#x1F91D;</div>
      <div class="result-panel">
        <div class="result-panel-label">With KSL Avatar</div>
        <video id="output-video" class="result-video" controls aria-label="Reel with KSL signing avatar">
          <track kind="captions" label="KSL Gloss"/>
        </video>
      </div>
    </div>
    <div class="gloss-result" aria-label="KSL Gloss output">
      <div class="gloss-label">KSL Gloss Output:</div>
      <div class="gloss-text" id="gloss-output"></div>
    </div>
    <div class="result-meta" id="result-meta"></div>
    <button class="btn btn-primary" id="download-btn" onclick="downloadResult()">
      Download KSL Video
    </button>
  `;
  section.classList.add("hidden");
  const btn = document.getElementById("process-btn");
  if (btn) {
    btn.disabled = false;
    const btnText = document.getElementById("process-btn-text");
    if (btnText) btnText.textContent = "Generate KSL";
  }
}

function showError(message) {
  hideProgress();
  const section = document.getElementById("result-section");
  if (!section) return;
  section.classList.remove("hidden");
  section.innerHTML = `
    <h3 style="color: #f87171; margin-bottom: 12px;">Processing Failed</h3>
    <p style="color: var(--text-secondary);">${message}</p>
    <button class="btn btn-ghost" style="margin-top: 20px;" onclick="resetAndHide()">
      Try Again
    </button>
  `;
  // Always re-enable button on error
  const btn = document.getElementById("process-btn");
  if (btn) {
    btn.disabled = false;
    const btnText = document.getElementById("process-btn-text");
    if (btnText) btnText.textContent = "Generate KSL";
  }
}

// ─── DOWNLOAD ─────────────────────────────────────────────────────────────
function downloadResult() {
  const btn = document.getElementById("download-btn");
  const url = btn.dataset.url;
  if (!url) return;

  const link = document.createElement("a");
  link.href = `${API_BASE.replace("/api", "")}${url}`;
  link.download = "sign_bridge_ksl_reel.mp4";
  link.click();
}

// ─── SMOOTH SCROLL FOR NAV ────────────────────────────────────────────────
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener("click", function(e) {
    e.preventDefault();
    const target = document.querySelector(this.getAttribute("href"));
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
});

// ─── INTERSECTION OBSERVER (entrance animations) ──────────────────────────
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = "1";
      entry.target.style.transform = "translateY(0)";
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll(".pipeline-step, .impact-card, .stack-card").forEach(el => {
  el.style.opacity = "0";
  el.style.transform = "translateY(24px)";
  el.style.transition = "opacity 0.5s ease, transform 0.5s ease";
  observer.observe(el);
});

console.log(`
╔══════════════════════════════════════════╗
║          SIGN BRIDGE v1.0.0              ║
║  KSL Real-Time Reel Accessibility        ║
║  Meta Global AI Hackathon 2026           ║
╚══════════════════════════════════════════╝
`);
