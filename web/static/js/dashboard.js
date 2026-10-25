// Advanced CCTV Analytics - Interactive Dashboard Script

let audioCtx = null;
let sirenOscillator = null;
let sirenGain = null;
let isAudioSirenPlaying = false;

// Initialize Web Audio API on first user gesture
function getAudioContext() {
  if (!audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) {
      audioCtx = new AudioContext();
    }
  }
  return audioCtx;
}

// Start browser-based emergency siren sound
function startBrowserSiren() {
  if (isAudioSirenPlaying) return;
  const ctx = getAudioContext();
  if (!ctx) return;

  if (ctx.state === 'suspended') {
    ctx.resume();
  }

  isAudioSirenPlaying = true;
  sirenOscillator = ctx.createOscillator();
  sirenGain = ctx.createGain();

  sirenOscillator.type = 'sawtooth';
  const now = ctx.currentTime;
  
  // Modulate frequency between 800Hz and 1600Hz
  sirenOscillator.frequency.setValueAtTime(800, now);
  const cycleTime = 0.6;
  for (let i = 0; i < 30; i++) {
    sirenOscillator.frequency.linearRampToValueAtTime(1600, now + i * cycleTime + 0.3);
    sirenOscillator.frequency.linearRampToValueAtTime(800, now + (i + 1) * cycleTime);
  }

  sirenGain.gain.setValueAtTime(0.15, now);
  sirenOscillator.connect(sirenGain);
  sirenGain.connect(ctx.destination);
  sirenOscillator.start();
}

function stopBrowserSiren() {
  if (!isAudioSirenPlaying) return;
  try {
    if (sirenOscillator) {
      sirenOscillator.stop();
      sirenOscillator.disconnect();
    }
    if (sirenGain) {
      sirenGain.disconnect();
    }
  } catch (e) {
    console.warn("Audio cleanup notice:", e);
  }
  isAudioSirenPlaying = false;
  sirenOscillator = null;
  sirenGain = null;
}

// Update UI Telemetry
async function pollSystemStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();

    // Telemetry
    document.getElementById('live-fps').textContent = data.fps || '0.0';
    document.getElementById('active-cam-name').textContent = `Cam #${data.active_camera_index} (${data.backend || 'MSMF/HW'})`;

    // Location
    if (data.location) {
      document.getElementById('location-display-text').textContent = data.location.location_name;
      document.getElementById('coords-display').textContent = `${data.location.latitude.toFixed(4)}° N, ${data.location.longitude.toFixed(4)}° E`;
      const mapsBtn = document.getElementById('btn-google-maps');
      if (mapsBtn && data.location.maps_url) {
        mapsBtn.href = data.location.maps_url;
      }
    }

    // SOS Phone
    if (data.sos_phone_number) {
      document.getElementById('sos-phone-display').textContent = data.sos_phone_number;
    }

    // Alarm & Hazard banner
    const alarmPill = document.getElementById('alarm-status-pill');
    const alarmText = document.getElementById('alarm-state-text');
    const hazardBanner = document.getElementById('hazard-alert-banner');
    const statusIndicator = document.getElementById('system-status-indicator');

    if (data.alarm_active) {
      alarmText.textContent = "ALARM ACTIVE!";
      alarmText.className = "telemetry-val status-danger";
      hazardBanner.style.display = 'flex';
      statusIndicator.className = "pulse-indicator danger";
      document.getElementById('banner-hazard-title').textContent = `CRITICAL HAZARD: ${data.last_hazard.toUpperCase()}`;
      startBrowserSiren();
    } else {
      alarmText.textContent = "STANDBY";
      alarmText.className = "telemetry-val status-safe";
      hazardBanner.style.display = 'none';
      statusIndicator.className = "pulse-indicator safe";
      stopBrowserSiren();
    }

    // Consecutive counters HUD
    const req = data.consecutive_required || 5;
    const counts = data.consecutive_counts || {};

    const updateHudBar = (hazard, elBar, elCount) => {
      const c = counts[hazard] || 0;
      const pct = Math.min(100, Math.round((c / req) * 100));
      document.getElementById(elBar).style.width = `${pct}%`;
      document.getElementById(elCount).textContent = `${c}/${req}`;
    };

    updateHudBar('fire', 'bar-fire', 'count-fire');
    updateHudBar('smoke', 'bar-smoke', 'count-smoke');
    updateHudBar('fall', 'bar-fall', 'count-fall');

  } catch (err) {
    console.error("Telemetry fetch error:", err);
  }
}

// Fetch and display incidents log
async function fetchIncidents() {
  try {
    const res = await fetch('/api/incidents');
    if (!res.ok) return;
    const incidents = await res.json();
    const container = document.getElementById('incident-container');

    if (!incidents || incidents.length === 0) {
      container.innerHTML = `<div class="empty-state">No hazards detected. System standing guard.</div>`;
      return;
    }

    container.innerHTML = incidents.slice(0, 10).map(inc => `
      <div class="incident-card">
        <div>
          <span class="incident-badge badge-${inc.hazard_type.toLowerCase()}">${inc.hazard_type}</span>
          <strong style="margin-left: 6px;">${inc.time_display}</strong>
          <div style="color: var(--text-muted); font-size: 0.72rem; margin-top: 2px;">
            Conf: ${(inc.confidence * 100).toFixed(1)}% | Cam: ${inc.camera_name}
          </div>
        </div>
        <div style="display: flex; gap: 6px;">
          <a href="${inc.maps_url}" target="_blank" class="btn btn-secondary btn-sm" title="View in Google Maps">📍 Map</a>
          <a href="/snapshots/${inc.snapshot_file}" target="_blank" class="btn btn-primary btn-sm" title="View Snapshot Evidence">📸 Evidence</a>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error("Incident fetch error:", err);
  }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
  // Start polling
  setInterval(pollSystemStatus, 800);
  setInterval(fetchIncidents, 3000);
  pollSystemStatus();
  fetchIncidents();

  // Silence Alarm Button
  document.getElementById('btn-silence-alarm').addEventListener('click', async () => {
    stopBrowserSiren();
    await fetch('/api/silence_alarm', { method: 'POST' });
    pollSystemStatus();
  });

  // Test Alarm Button
  document.getElementById('btn-test-alarm').addEventListener('click', async () => {
    startBrowserSiren();
    await fetch('/api/test_alarm', { method: 'POST' });
    pollSystemStatus();
  });

  // Test SOS Dispatch Button
  document.getElementById('btn-test-sos').addEventListener('click', async () => {
    startBrowserSiren();
    const res = await fetch('/api/test_sos', { method: 'POST' });
    if (res.ok) {
      alert("🚨 SOS Emergency Alert Dispatched! Check incident log and terminal console for payload.");
      fetchIncidents();
      pollSystemStatus();
    }
  });

  // Settings form submission
  document.getElementById('settings-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const sos_phone = document.getElementById('input-sos-phone').value;
    const conf = parseFloat(document.getElementById('input-conf').value);
    const frames = parseInt(document.getElementById('input-frames').value);

    const payload = {
      sos_phone_number: sos_phone,
      confidence_threshold: conf,
      consecutive_frames_required: frames
    };

    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      alert("Configuration updated successfully!");
      pollSystemStatus();
    }
  });
});
