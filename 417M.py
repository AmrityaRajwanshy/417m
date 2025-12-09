import http.server
import socket
import socketserver
import webbrowser
import sys
import os

# --- HTML CONTENT ---
# This matches the content of 417M.html we designed.
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>10m Distance Check</title>
    <style>
        body {
            background-color: #121212;
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            text-align: center;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 90vh;
            margin: 0;
            overflow: hidden; 
        }
        h1 { margin-bottom: 5px; font-size: 1.5rem; }
        .coords { font-family: monospace; font-size: 0.9rem; color: #aaaaaa; margin-bottom: 20px; }
        
        .card {
            background: #1e1e1e;
            padding: 20px;
            border-radius: 16px;
            width: 90%;
            max-width: 400px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .display-box {
            background: #2c2c2c;
            border-radius: 12px;
            padding: 20px;
            min-height: 100px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            transition: background-color 0.3s ease;
        }

        #distanceVal {
            font-size: 3.5rem;
            font-weight: 800;
            margin: 0;
            line-height: 1;
        }
        #message {
            font-size: 1.5rem;
            font-weight: 600;
            margin-top: 10px;
            text-transform: uppercase;
        }
        
        button {
            width: 100%;
            padding: 18px;
            font-size: 1.2rem;
            font-weight: bold;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            transition: transform 0.1s, opacity 0.2s;
            color: white;
        }
        button:active { transform: scale(0.98); }
        button:disabled { opacity: 0.5; cursor: not-allowed; }

        .btn-blue { background-color: #2196F3; }
        .btn-green { background-color: #4CAF50; }
        .btn-red { background-color: #f44336; }
        
        .log-box {
            margin-top: 20px;
            text-align: left;
            font-size: 0.8rem;
            color: #888;
            max-height: 150px;
            overflow-y: auto;
            width: 100%;
            border-top: 1px solid #333;
            padding-top: 10px;
        }

        .status-idle { background: #2c2c2c; color: #fff; }
        .status-far { background: #c62828; color: #fff; }
        .status-close { background: #fbc02d; color: #000; }
        .status-perfect { background: #2e7d32; color: #fff; }
        
        .pulse { animation: pulse 1.5s infinite; }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.6; }
            100% { opacity: 1; }
        }
    </style>
</head>
<body>

    <h1>10m Check</h1>
    <div class="coords">GPS Acc: <span id="accuracy">--</span> m</div>

    <div class="card">
        <div id="statusBox" class="display-box status-idle">
            <div id="distanceVal">--</div>
            <div id="message">Ready</div>
        </div>

        <button id="btnStart" class="btn-blue" onclick="captureStart()">📍 Capture START</button>
        <button id="btnStop" class="btn-red" onclick="stopTracking()" style="display:none;">⏹ Stop / Reset</button>
        <button id="btnSave" class="btn-green" onclick="saveTarget()" disabled>💾 Capture TARGET</button>

        <div class="log-box" id="logBox">
            <div><strong>Saved Locations:</strong></div>
        </div>
    </div>

    <script>
        const TARGET_DIST = 10.0;
        const TOLERANCE = 0.5; 
        
        let startPos = null;
        let watchId = null;
        let audioCtx = null;
        let lastBeepTime = 0;

        const elDist = document.getElementById('distanceVal');
        const elMsg = document.getElementById('message');
        const elBox = document.getElementById('statusBox');
        const elAcc = document.getElementById('accuracy');
        const btnStart = document.getElementById('btnStart');
        const btnStop = document.getElementById('btnStop');
        const btnSave = document.getElementById('btnSave');
        const logBox = document.getElementById('logBox');

        function initAudio() {
            if (!audioCtx) {
                audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }
        }

        function playBeep(freq = 800, duration = 0.1) {
            if (!audioCtx) return;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.frequency.value = freq;
            osc.type = 'sine';
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            gain.gain.setValueAtTime(0.1, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + duration);
            osc.stop(audioCtx.currentTime + duration);
        }

        function haversine(lat1, lon1, lat2, lon2) {
            const R = 6371000; 
            const dLat = (lat2 - lat1) * Math.PI / 180;
            const dLon = (lon2 - lon1) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * 
                      Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            return R * c;
        }

        function handleError(err) {
            console.warn('GPS Error:', err);
            elAcc.innerText = "Err";
            elMsg.innerText = "GPS Error";
        }

        function captureStart() {
            initAudio();
            if (!navigator.geolocation) {
                alert("Geolocation not supported");
                return;
            }
            btnStart.style.display = 'none';
            btnStop.style.display = 'block';
            elMsg.innerText = "Acquiring...";
            elBox.className = "display-box status-idle pulse";

            watchId = navigator.geolocation.watchPosition(
                (pos) => {
                    const lat = pos.coords.latitude;
                    const lng = pos.coords.longitude;
                    const acc = pos.coords.accuracy;
                    elAcc.innerText = acc.toFixed(1);

                    if (!startPos) {
                        startPos = { lat, lng };
                        elMsg.innerText = "Start Set. Move!";
                        btnSave.disabled = false;
                        const time = new Date().toLocaleTimeString();
                        logBox.innerHTML += `<div>[${time}] Start: ${lat.toFixed(6)}, ${lng.toFixed(6)}</div>`;
                    } else {
                        const dist = haversine(startPos.lat, startPos.lng, lat, lng);
                        updateGuidance(dist);
                    }
                },
                handleError,
                { enableHighAccuracy: true, maximumAge: 0, timeout: 5000 }
            );
        }

        function updateGuidance(dist) {
            elDist.innerText = dist.toFixed(1) + "m";
            const diff = dist - TARGET_DIST;
            
            if (Math.abs(diff) <= TOLERANCE) {
                elBox.className = "display-box status-perfect";
                elMsg.innerText = "PERFECT - STOP";
                const now = Date.now();
                if (now - lastBeepTime > 800) {
                    playBeep(1200, 0.15);
                    lastBeepTime = now;
                }
            } else if (dist < (TARGET_DIST - TOLERANCE)) {
                elBox.className = "display-box status-close";
                elMsg.innerText = "MOVE AHEAD ⬆️";
            } else {
                elBox.className = "display-box status-far";
                elMsg.innerText = "MOVE BACK ⬇️";
            }
        }

        function saveTarget() {
            if (!startPos) return;
            const currentDistStr = elDist.innerText;
            const time = new Date().toLocaleTimeString();
            logBox.innerHTML += `<div>[${time}] <strong>Saved: ${currentDistStr}</strong></div>`;
            logBox.scrollTop = logBox.scrollHeight;
            playBeep(1500, 0.3);
        }

        function stopTracking() {
            if (watchId) {
                navigator.geolocation.clearWatch(watchId);
                watchId = null;
            }
            startPos = null;
            btnStart.style.display = 'block';
            btnStop.style.display = 'none';
            btnSave.disabled = true;
            elDist.innerText = "--";
            elMsg.innerText = "Ready";
            elBox.className = "display-box status-idle";
            elAcc.innerText = "--";
        }
    </script>
</body>
</html>
"""

# --- SERVER CONSTANTS ---
PORT = 8000

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode('utf-8'))
    
    def log_message(self, format, *args):
        # Silence default logging
        return

def run_server():
    ip = get_local_ip()
    url = f"http://{ip}:{PORT}"
    
    print("-" * 50)
    print(f"Server started on: {url}")
    print("1. Connect mobile to same Wi-Fi")
    print("2. Open the URL above on your mobile phone")
    print("-" * 50)
    
    # Try to open locally too
    webbrowser.open(f"http://localhost:{PORT}")
    
    server = socketserver.TCPServer(('0.0.0.0', PORT), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Server stopped.")

if __name__ == "__main__":
    run_server()
