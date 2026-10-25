# 🚨 Advanced CCTV Analytics: AI Hazard Detection & SOS Pinpointing

An intelligent, edge-capable CCTV video analytics platform built according to the system specifications for real-time hazard detection (fire, smoke, falls, intrusions), multi-frame persistence verification, automatic evidence snapshotting, emergency audible alarm sirens, and instant SOS alerts with live Google Maps pinpointing to designated emergency contacts.

---

## 📋 System Architecture & Workflow

Based on the official CCTV analytics pipeline:

```
+-----------------------------------+
|        CCTV Camera Feed           |
| (Enforces Connected Devices Only) |
+-----------------+-----------------+
                  |
                  v
+-----------------+-----------------+
|        Frame Extraction           |
|    (OpenCV Resize & Denoise)      |
+-----------------+-----------------+
                  |
                  v
+-----------------+-----------------+
|      Hazard Detection Model       |
|    (YOLOv8: Fire, Smoke, Fall)    |
+-----------------+-----------------+
                  |
                  v
+-----------------+-----------------+
|        Hazard Confirmed?          |
|  (Confidence >= 70% & 5+ Frames)  |
+--------+-----------------+--------+
         |                 |
     [No]|             [Yes|
         v                 v
+--------+--------+  +-----+-----------------+
| Keep Monitoring |  |     Save Evidence     |
|   (Next Frame)  |  | (Snapshot, Timestamp) |
+-----------------+  +-----+-----------------+
                           |
                           v
                     +-----+-----------------+
                     |   Fetch Live Location |
                     |   (GPS / Google Maps) |
                     |   & Sound Audio Siren |
                     +-----+-----------------+
                           |
                           v
                     +-----+-----------------+
                     |    Send SOS Alert     |
                     | (SMS / WhatsApp / Log)|
                     +-----+-----------------+
                           |
                           v
                     +-----+-----------------+
                     | Phone Receives Alert  |
                     | (Hazard + Maps Pin)   |
                     +-----------------------+
```

---

## 🎯 Core Features

1. **Only Connected Cameras Enforced**:
   - Strictly scans and binds to physical hardware cameras (e.g. `Camera #0`).
   - Mock videos, synthetic scenes, and fake demo cameras are strictly prohibited in the camera pipeline.

2. **Trained Custom YOLOv8 Hazard Model**:
   - Pre-trained and fine-tuned on CCTV fire and smoke hazard benchmark datasets.
   - Saves model weights to `models/hazard_best.pt`.
   - Dedicated `model_training/` folder with Kaggle dataset integration.

3. **Multi-Frame Verification & False Alarm Suppression**:
   - Requires hazards to persist for **5 or more consecutive frames** with high confidence (configurable in `config.json`).
   - Enforces a **60-second cooldown suppression window** per hazard type to eliminate duplicate notifications.

4. **Audible Emergency Siren Alarm**:
   - Background multi-tone audio siren utilizing Windows `winsound.Beep` for local alerts.
   - In-browser synthesized emergency siren powered by HTML5 Web Audio API.

5. **Live Location Pinpointing & Evidence Capture**:
   - Automatically generates Google Maps pinpoint links: `https://maps.google.com/?q={lat},{lon}`.
   - Saves high-resolution timestamped evidence snapshots (`evidence/snapshots/`) with red alert overlays and telemetry.

6. **Multi-Channel SOS Alert Dispatcher**:
   - Sends formatted emergency alerts to the designated SOS phone number:
     ```
     🚨 EMERGENCY SOS ALERT: FIRE DETECTED!
     Camera: Gate 1 - Main Perimeter | Time: 14:32:10
     Confidence: 89.4%
     Location: https://maps.google.com/?q=28.6139,77.2090
     Evidence: evidence/snapshots/hazard_fire_20261011_233000.jpg
     ```
   - Integrates Twilio SMS, WhatsApp, Telegram Bot API, and permanent incident log JSON.

7. **Interactive Command Center Web Dashboard**:
   - Real-time MJPEG live stream with bounding boxes, HUD counter, and FPS tracker.
   - Interactive alarm controls (Test Alarm, Silence Alarm, Test SOS).
   - Evidence gallery and recent incidents table with 1-click Google Maps viewer.

---

## 📁 Project Directory Structure

```
advanced_cctv_analytics/
│
├── config.json                     # System configuration (SOS number, thresholds, GPS, Twilio)
├── config.py                       # Configuration loader and updater
├── main.py                         # Primary application runner (Web Dashboard, Window, Headless)
├── web_app.py                      # FastAPI live streaming server and REST API
├── requirements.txt                # Python dependencies
│
├── model_training/                 # Model training folder
│   ├── download_kaggle_dataset.py  # Kaggle API & verified hazard dataset downloader
│   ├── train_model.py              # YOLOv8 training script
│   └── datasets/                   # Datasets stored for model training
│       └── hazard_dataset/
│           ├── data.yaml           # YOLO configuration
│           ├── images/ (train, val)
│           └── labels/ (train, val)
│
├── models/
│   └── hazard_best.pt              # The trained YOLO hazard detector weights
│
├── core/
│   ├── camera.py                   # Hardware camera scanner (connected cameras only)
│   ├── preprocessor.py             # OpenCV frame resize & denoise
│   ├── detector.py                 # Multi-frame YOLO hazard & anomaly detector
│   ├── alarm.py                    # Multi-tone audio siren alarm manager
│   ├── locator.py                  # Geolocation & Google Maps pinpoint link generator
│   ├── alert_dispatcher.py         # Evidence snapshotting & SOS alert sender
│   └── analytics_engine.py         # Unified CCTV analytics engine orchestrator
│
├── evidence/
│   ├── snapshots/                  # Saved hazard evidence photos
│   └── logs/incidents.json         # Incident records and SOS dispatch logs
│
└── web/
    ├── templates/index.html        # Modern CCTV Command Center UI
    └── static/
        ├── css/style.css           # Styling with safety indicators
        └── js/dashboard.js         # Client telemetry, Web Audio siren, and controls
```

---

## 🚀 Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Model Training & Kaggle Datasets
The model is already trained and exported to `models/hazard_best.pt`. If you wish to retrain or download datasets from Kaggle:

To download from Kaggle using your Kaggle API key:
```bash
# Set your Kaggle credentials
$env:KAGGLE_USERNAME = "your_username"
$env:KAGGLE_KEY = "your_api_key"

# Download Kaggle hazard dataset
python model_training/download_kaggle_dataset.py --kaggle-dataset sayedgamal99/smoke-fire-detection-yolo
```

To run training on the prepared hazard dataset:
```bash
python model_training/train_model.py 5
```

### 3. Launching CCTV Analytics

#### Mode A: Interactive Command Center Dashboard (Recommended)
```bash
python main.py
```
Opens the live dashboard in your web browser at `http://127.0.0.1:8000`.

#### Mode B: Desktop OpenCV Window
```bash
python main.py --window
```

#### Mode C: Headless Edge Monitor
```bash
python main.py --headless
```

---

## ⚙️ Configuration (`config.json`)

You can edit `config.json` directly or use the Web Dashboard UI:
```json
{
  "camera": {
    "device_index": 0,
    "camera_name": "Gate 1 - Main Perimeter",
    "denoise": true
  },
  "detection": {
    "model_path": "models/hazard_best.pt",
    "confidence_threshold": 0.70,
    "consecutive_frames_required": 5,
    "cooldown_seconds": 60
  },
  "sos_alert": {
    "sos_phone_number": "+1234567890",
    "channels": {
      "sms": false,
      "whatsapp": false,
      "telegram": false,
      "local_logger": true
    }
  }
}
```
