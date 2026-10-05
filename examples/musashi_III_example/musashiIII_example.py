# app.py
# Musashi III Web Control Panel (Port 8082)
# See: docs/architecture/context.md
# English comments only

try:
    import eventlet
    eventlet.monkey_patch()
except Exception as _e:
    print(f"[WARNING] Eventlet initialization warning: {_e}")

import os
import sys
import json
import subprocess
import threading
import re
import time
import signal
import atexit
import tempfile

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

app = Flask(__name__, template_folder='templates', static_folder='static')
socketio = SocketIO(app, cors_allowed_origins="*")

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        return ('', 204)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options_preflight(path=''):
    return ('', 204)

# State files to persist process metadata across restarts
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
PID_PATH = os.path.join(BASE_DIR, '.musashi_iii_process.pid')
MODE_PATH = os.path.join(BASE_DIR, '.musashi_iii_process.mode')
DESIRED_STATE_PATH = os.path.join(BASE_DIR, '.musashi_iii_desired_state.json')
LOG_PATH = os.path.join(BASE_DIR, 'musashi_iii_pipeline.log')

# Global synchronization and monitoring variables
tail_thread = None
tail_lock = threading.Lock()
stop_tail_event = threading.Event()
process_lifecycle_lock = threading.Lock()
shutdown_lock = threading.Lock()
_shutting_down = False
last_stats = {}

def read_config():
    """Reads configuration parameters from config.json."""
    default_port = "COM1" if sys.platform == "win32" else "/dev/cu.usbserial-A600bsZD"
    default_config = {
        "startup": {
            "auto_start_on_startup": True,
            "auto_start_mode": "mockup"
        },
        "serial": {
            "port": default_port,
            "baudrate": 9600,
            "timeout": 2.0,
            "channel": 1
        },
        "database": {
            "db_type": "postgresql",
            "db_name": "mddp_lab",
            "table_name": "musashi_telemetry",
            "host": "100.81.77.113",
            "port": 10001,
            "user": "admin",
            "password": "admin",
            "description": "Database storage for MUSASHI Super ΣCMII Dispenser telemetry data"
        },
        "acquisition": {
            "interval_time": 1,
            "max_retries": 3
        }
    }
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                # Ensure defaults are present for missing sections
                for key in default_config:
                    if key not in cfg:
                        cfg[key] = default_config[key]
                return cfg
    except Exception as e:
        print(f"[ERROR] Reading config.json: {e}")
    return default_config

def validate_config(config_data):
    """
    Validates configuration schema and parameter values.
    Returns (is_valid: bool, error_message: str).
    """
    if not isinstance(config_data, dict):
        return False, "Configuration payload must be a JSON object"

    # Acquisition section validation
    if 'acquisition' in config_data:
        acq = config_data['acquisition']
        if not isinstance(acq, dict):
            return False, "'acquisition' must be an object"
        if 'interval_time' in acq:
            try:
                interval = float(acq['interval_time'])
                if interval <= 0:
                    return False, "'interval_time' must be a positive number (> 0)"
            except (ValueError, TypeError):
                return False, "'interval_time' must be a valid numeric value"

    # Serial section validation
    if 'serial' in config_data:
        ser = config_data['serial']
        if not isinstance(ser, dict):
            return False, "'serial' must be an object"
        if 'baudrate' in ser:
            try:
                baud = int(ser['baudrate'])
                if baud <= 0:
                    return False, "'baudrate' must be a positive integer"
            except (ValueError, TypeError):
                return False, "'baudrate' must be a valid integer"
        if 'timeout' in ser:
            try:
                timeout = float(ser['timeout'])
                if timeout <= 0:
                    return False, "'timeout' must be a positive number"
            except (ValueError, TypeError):
                return False, "'timeout' must be a valid numeric value"

    # Database section validation
    if 'database' in config_data and not isinstance(config_data['database'], dict):
        return False, "'database' must be an object"

    return True, ""

def write_config(config_data):
    """
    Writes configuration parameters atomically to config.json using NamedTemporaryFile
    and os.replace() to prevent file corruption (e.g. 0-byte file on sudden crash/power cut).
    """
    temp_file = None
    try:
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=BASE_DIR,
            delete=False,
            prefix='.config_',
            suffix='.tmp'
        )
        json.dump(config_data, temp_file, indent=2)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()

        os.replace(temp_file.name, CONFIG_PATH)
        return True
    except Exception as e:
        print(f"[ERROR] Writing config.json atomically: {e}")
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.remove(temp_file.name)
            except OSError:
                pass
        return False

def read_desired_state():
    """Reads persistent desired state metadata across reboots."""
    try:
        if os.path.exists(DESIRED_STATE_PATH):
            with open(DESIRED_STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[ERROR] Reading desired state: {e}")
    return {"is_running": False, "mode": "mockup"}

def write_desired_state(is_running, mode="mockup"):
    """Writes persistent desired state metadata atomically across system reboots."""
    temp_file = None
    try:
        temp_file = tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=BASE_DIR,
            delete=False,
            prefix='.desired_state_',
            suffix='.tmp'
        )
        json.dump({"is_running": is_running, "mode": mode}, temp_file, indent=2)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        os.replace(temp_file.name, DESIRED_STATE_PATH)
    except Exception as e:
        print(f"[ERROR] Writing desired state: {e}")
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.remove(temp_file.name)
            except OSError:
                pass

def is_pid_running(pid):
    """
    Cross-platform check that verifies the process actually exists,
    is not a zombie process, and that its command line contains 'read_musashi.py'
    so that an unrelated recycled PID is NEVER falsely identified or killed.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False

    # 1. Prefer psutil if available
    if PSUTIL_AVAILABLE:
        try:
            proc = psutil.Process(pid)
            if not proc.is_running():
                return False
            if proc.status() == psutil.STATUS_ZOMBIE:
                return False
            cmdline = proc.cmdline()
            cmdline_str = " ".join(cmdline)
            return "read_musashi.py" in cmdline_str
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False
        except Exception:
            pass

    # 2. Windows Fallbacks (PowerShell / WMIC)
    if sys.platform == "win32":
        try:
            cmd = f'powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \\"ProcessId={pid}\\").CommandLine"'
            out = subprocess.check_output(cmd, shell=True, text=True, timeout=2).strip()
            if "read_musashi.py" in out:
                return True
        except Exception:
            pass
        try:
            out = subprocess.check_output(f'wmic process where processid={pid} get commandline', shell=True, text=True, timeout=2)
            if "read_musashi.py" in out:
                return True
        except Exception:
            pass
        return False

    # 3. Linux /proc Filesystem Check
    proc_dir = f"/proc/{pid}"
    if os.path.exists(proc_dir):
        try:
            status_path = f"{proc_dir}/status"
            if os.path.exists(status_path):
                with open(status_path, "r", errors="ignore") as sf:
                    for sline in sf:
                        if sline.startswith("State:") and "Z" in sline:
                            return False
            cmdline_path = f"{proc_dir}/cmdline"
            if os.path.exists(cmdline_path):
                with open(cmdline_path, "rb") as cf:
                    cmd = cf.read().decode("utf-8", errors="ignore").replace("\0", " ")
                    return "read_musashi.py" in cmd
        except (OSError, IOError):
            return False

    # 4. POSIX ps command check (macOS / BSD / Linux fallback)
    try:
        out = subprocess.check_output(["ps", "-p", str(pid), "-o", "stat=,command="], text=True, stderr=subprocess.DEVNULL, timeout=2).strip()
        if not out:
            return False
        parts = out.split(None, 1)
        stat = parts[0]
        cmd = parts[1] if len(parts) > 1 else ""
        if stat.startswith("Z"):
            return False
        return "read_musashi.py" in cmd
    except Exception:
        return False

def get_running_process():
    """Retrieves the running process PID and mode if active and verified."""
    if os.path.exists(PID_PATH) and os.path.exists(MODE_PATH):
        try:
            with open(PID_PATH, 'r') as f:
                pid = int(f.read().strip())
            with open(MODE_PATH, 'r') as f:
                mode = f.read().strip()
            
            if is_pid_running(pid):
                return pid, mode
            else:
                # Clean up stale metadata files from previous dead or recycled process
                try: os.remove(PID_PATH)
                except OSError: pass
                try: os.remove(MODE_PATH)
                except OSError: pass
        except Exception as e:
            print(f"[ERROR] Checking active PID file: {e}")
    return None, None

def terminate_pid(pid):
    """
    Terminates process by PID cross-platform.
    On Windows: uses taskkill /pid {pid} /t /f.
    On POSIX: uses process group signaling (os.killpg) and reaps zombies with os.waitpid(pid, os.WNOHANG)
    so it does not hang for 3 seconds on zombie processes.
    """
    if not isinstance(pid, int) or pid <= 0:
        return

    if sys.platform == "win32":
        try:
            subprocess.run(f"taskkill /pid {pid} /t /f", shell=True)
        except Exception as e:
            print(f"[ERROR] Terminating Windows PID {pid}: {e}")
    else:
        try:
            pgid = None
            try:
                pgid = os.getpgid(pid)
            except (ProcessLookupError, OSError):
                pass

            current_pgrp = None
            try:
                current_pgrp = os.getpgrp()
            except Exception:
                pass

            # Graceful SIGTERM first
            if pgid is not None and pgid != current_pgrp:
                try:
                    os.killpg(pgid, signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    pass
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    pass

            # Wait up to 3 seconds for exit, reaping child zombies immediately with WNOHANG
            for _ in range(30):
                try:
                    wpid, _ = os.waitpid(pid, os.WNOHANG)
                    if wpid != 0:
                        return
                except ChildProcessError:
                    pass

                if not is_pid_running(pid):
                    return
                time.sleep(0.1)

            # Force kill with SIGKILL if still running
            if pgid is not None and pgid != current_pgrp:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass

            # Reap zombie after SIGKILL
            try:
                os.waitpid(pid, os.WNOHANG)
            except (ChildProcessError, OSError):
                pass

        except Exception as e:
            print(f"[ERROR] Terminating POSIX PID {pid}: {e}")

def cleanup_on_exit():
    """Cleanup hook to ensure worker process is terminated when app shuts down."""
    global _shutting_down
    with shutdown_lock:
        if _shutting_down:
            return
        _shutting_down = True

    try:
        pid, _ = get_running_process()
        if pid is not None:
            print(f"[SYSTEM] Application shutting down. Terminating worker process (PID: {pid})...")
            terminate_pid(pid)
            if os.path.exists(PID_PATH):
                try: os.remove(PID_PATH)
                except OSError: pass
            if os.path.exists(MODE_PATH):
                try: os.remove(MODE_PATH)
                except OSError: pass
    except Exception as e:
        print(f"[ERROR] Error during cleanup on exit: {e}")

atexit.register(cleanup_on_exit)

def signal_handler(signum, frame):
    """Signal handler for SIGINT and SIGTERM."""
    print(f"[SYSTEM] Received signal {signum}, initiating clean shutdown...")
    cleanup_on_exit()
    sys.exit(0)

try:
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
except Exception as _se:
    print(f"[WARNING] Could not register signal handlers: {_se}")

def sanitize_error(error_msg, sensitive_values=None):
    """Sanitizes exception messages to prevent leaking credentials in HTTP responses."""
    sanitized = str(error_msg)
    if sensitive_values:
        for val in sensitive_values:
            if val and isinstance(val, str) and len(val) > 1:
                sanitized = sanitized.replace(val, "******")
    sanitized = re.sub(r':([^:@\s/]+)@', ':******@', sanitized)
    return sanitized

# Regex to extract statistics from the log file
# E.g.: [STATS] polled=1 | written=1 | db_errors=0 | pressure_kpa=50.0 | time_ms=250 | vacuum_kpa=0.50 | mode=Sigma Timed | product=PROD_MOCK
STATS_REGEX = re.compile(
    r"\[STATS\] polled=(?P<polled>[0-9,]+) \| written=(?P<written>[0-9,]+) \| db_errors=(?P<errors>[0-9]+) \| pressure_kpa=(?P<press>[0-9\.]+) \| time_ms=(?P<time>[0-9\.]+) \| vacuum_kpa=(?P<vac>[0-9\.]+) \| mode=(?P<mode>[^\|]+) \| product=(?P<prod>.*)"
)

def parse_and_emit_stats(line):
    """Parses stats from a line and updates global caches."""
    global last_stats
    match = STATS_REGEX.search(line)
    if match:
        last_stats = {
            'polled': match.group('polled'),
            'written': match.group('written'),
            'errors': match.group('errors'),
            'pressure_kpa': match.group('press'),
            'time_ms': match.group('time'),
            'vacuum_kpa': match.group('vac'),
            'mode_name': match.group('mode').strip(),
            'product_name': match.group('prod').strip()
        }
        socketio.emit('stats_update', last_stats)

def tail_log_file():
    """
    Background loop tailing the physical log file to feed sockets.
    Throttles PID liveness check to once every 2 seconds to avoid CPU spikes.
    Handles log file truncation on worker restarts.
    """
    global last_stats
    print("[SYSTEM] Musashi III Log tailing thread started.")
    
    while not os.path.exists(LOG_PATH) and not stop_tail_event.is_set():
        time.sleep(0.2)
        
    try:
        with open(LOG_PATH, 'r', errors='replace') as f:
            f.seek(0, os.SEEK_END)
            last_pid_check = 0.0
            PID_CHECK_INTERVAL = 2.0
            
            while not stop_tail_event.is_set():
                now = time.time()
                if now - last_pid_check >= PID_CHECK_INTERVAL:
                    last_pid_check = now
                    pid, _ = get_running_process()
                    if pid is None:
                        port = read_config().get('serial', {}).get('port', 'N/A')
                        socketio.emit('status_change', {
                            'is_running': False,
                            'mode': 'mockup',
                            'port': port
                        })
                        if os.path.exists(PID_PATH):
                            try: os.remove(PID_PATH)
                            except OSError: pass
                        if os.path.exists(MODE_PATH):
                            try: os.remove(MODE_PATH)
                            except OSError: pass
                        break
                        
                line = f.readline()
                if not line:
                    # Check for log file truncation (e.g. session restarted and overwritten)
                    try:
                        if os.path.exists(LOG_PATH):
                            current_size = os.path.getsize(LOG_PATH)
                            if f.tell() > current_size:
                                f.seek(0, os.SEEK_SET)
                    except OSError:
                        pass
                    time.sleep(0.1)
                    continue
                
                decoded_line = line.strip()
                socketio.emit('log_update', {'log': decoded_line})
                parse_and_emit_stats(decoded_line)
                
    except Exception as e:
        print(f"[ERROR] Error tailing log file: {e}")
    finally:
        print("[SYSTEM] Musashi III Log tailing thread finished.")

def start_tailing():
    """Starts a new background tailing thread if not active, synchronized by tail_lock."""
    global tail_thread, stop_tail_event
    with tail_lock:
        stop_tail_event.clear()
        if tail_thread is None or not tail_thread.is_alive():
            tail_thread = threading.Thread(target=tail_log_file, daemon=True)
            tail_thread.start()

def get_last_logs(count=50):
    """Retrieves last few log lines for newly connected clients."""
    if not os.path.exists(LOG_PATH):
        return []
    try:
        with open(LOG_PATH, 'r', errors='replace') as f:
            lines = f.readlines()
            return [line.strip() for line in lines[-count:]]
    except Exception as e:
        print(f"[ERROR] Reading historical logs: {e}")
        return []

def scan_host_serial_devices():
    """Scans host PC for connected USB-serial ports and COM interfaces."""
    detected = []
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        for p in ports:
            desc = p.description if p.description else p.device
            mfg = getattr(p, 'manufacturer', None) or 'USB Serial Device'
            detected.append({
                'id': p.device,
                'name': f"{p.device} ({desc})",
                'type': 'RS-232 / USB Serial Port',
                'port': p.device,
                'vendor': mfg,
                'hwid': getattr(p, 'hwid', '')
            })
    except Exception as e:
        print(f"[SCAN] Serial port enumeration note: {e}")

    # Fallback default ports for Unix / Windows
    if sys.platform != "win32":
        detected.append({
            'id': '/dev/cu.usbserial-A600bsZD',
            'name': 'Default Musashi RS-232 Port (/dev/cu.usbserial-A600bsZD)',
            'type': 'Configured POSIX Device',
            'port': '/dev/cu.usbserial-A600bsZD',
            'vendor': 'FTDI'
        })
        detected.append({
            'id': '/dev/ttyUSB0',
            'name': 'Linux USB Serial Port (/dev/ttyUSB0)',
            'type': 'Linux TTY Serial',
            'port': '/dev/ttyUSB0',
            'vendor': 'Generic Serial'
        })
    else:
        detected.append({
            'id': 'COM1',
            'name': 'COM1 (Standard Windows Serial Port)',
            'type': 'Windows COM Port',
            'port': 'COM1',
            'vendor': 'System Port'
        })

    detected.append({
        'id': 'MOCK',
        'name': 'MOCK Virtual Hardware (Synthetic Simulation)',
        'type': 'Mockup / Driverless',
        'port': 'MOCK',
        'vendor': 'Software Mock'
    })

    # Deduplicate by 'id'
    seen = set()
    unique = []
    for d in detected:
        if d['id'] not in seen:
            seen.add(d['id'])
            unique.append(d)

    return unique

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(read_config())

@app.route('/api/config', methods=['POST'])
def save_config():
    config_data = request.json
    if not config_data:
        return jsonify({'status': 'error', 'message': 'Invalid payload'}), 400

    is_valid, err_msg = validate_config(config_data)
    if not is_valid:
        return jsonify({'status': 'error', 'message': err_msg}), 400

    if write_config(config_data):
        return jsonify({'status': 'success', 'config': config_data})
    return jsonify({'status': 'error', 'message': 'Failed to save configuration.'}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    pid, mode = get_running_process()
    cfg = read_config()
    serial_port = cfg.get('serial', {}).get('port', 'N/A')
    mode_val = mode or 'mockup'
    is_running = pid is not None
    return jsonify({
        'service_name': 'MUSASHI III',
        'port': 8082,
        'is_running': is_running,
        'status': 'running' if is_running else 'stopped',
        'mode': mode_val,
        'run_mode': mode_val,
        'pid': pid,
        'serial_port': serial_port,
        'db_type': cfg.get('database', {}).get('db_type', 'sqlite')
    })

@app.route('/api/scan_serial', methods=['GET'])
def api_scan_serial():
    """Returns JSON list of detected serial interfaces on host PC."""
    devices = scan_host_serial_devices()
    return jsonify({
        'status': 'success',
        'count': len(devices),
        'devices': devices
    })

@app.route('/api/test_db', methods=['POST'])
def test_db():
    req = request.get_json() or {}
    db_cfg = req.get('database') or read_config().get('database', {})
    db_type = db_cfg.get('db_type', 'sqlite')
    
    if db_type in ('postgresql', 'timescaledb'):
        password = str(db_cfg.get('password', 'admin'))
        user = str(db_cfg.get('user', 'admin'))
        host = str(db_cfg.get('host', 'localhost'))
        try:
            port = int(db_cfg.get('port', 5432))
        except (ValueError, TypeError):
            port = 5432
        dbname = str(db_cfg.get('db_name', 'mddp_lab'))
        try:
            import psycopg2
            conn = psycopg2.connect(
                dbname=dbname,
                user=user,
                password=password,
                host=host,
                port=port,
                connect_timeout=3
            )
            conn.close()
            return jsonify({'success': True, 'message': f'{db_type.upper()} connection to {host}:{port}/{dbname} successful!'})
        except Exception as e:
            safe_msg = sanitize_error(e, [password])
            return jsonify({'success': False, 'message': f'{db_type.upper()} connection error: {safe_msg}'})
            
    elif db_type == 'influxdb':
        url = db_cfg.get('influx_url', 'http://localhost:8086').rstrip('/')
        token = str(db_cfg.get('influx_token', ''))
        org = db_cfg.get('influx_org', 'mddp')
        bucket = db_cfg.get('influx_bucket', 'musashi_telemetry')

        target_url = f"{url}/health"
        headers = {"User-Agent": "MusashiIII-TestClient"}
        if token:
            headers["Authorization"] = f"Token {token}"

        try:
            import urllib.request
            req_obj = urllib.request.Request(target_url, headers=headers, method="GET")
            with urllib.request.urlopen(req_obj, timeout=3.0) as resp:
                if resp.status in (200, 204):
                    return jsonify({'success': True, 'message': f'InfluxDB server at {url} is HEALTHY! (Org: {org}, Bucket: {bucket})'})
                else:
                    return jsonify({'success': False, 'message': f'InfluxDB returned HTTP status {resp.status}'})
        except Exception as e:
            safe_msg = sanitize_error(e, [token])
            return jsonify({'success': False, 'message': f'InfluxDB connection error: {safe_msg}'})
            
    else:
        try:
            import sqlite3
            db_name = db_cfg.get('sqlite_path') or db_cfg.get('db_name', 'musashi_data.db')
            db_path = db_name if os.path.isabs(db_name) else os.path.join(BASE_DIR, db_name)
            conn = sqlite3.connect(db_path)
            conn.close()
            return jsonify({'success': True, 'message': f'SQLite connection to {db_name} successful!'})
        except Exception as e:
            safe_msg = sanitize_error(e)
            return jsonify({'success': False, 'message': f'SQLite connection error: {safe_msg}'})

@app.route('/api/test_serial', methods=['POST'])
def test_serial():
    pid, run_mode = get_running_process()
    if pid is not None:
        return jsonify({
            'success': False,
            'message': f'Serial port is currently in use by active worker (PID: {pid}, mode: {run_mode}). Stop ingestion before testing.'
        })

    req = request.get_json() or {}
    serial_cfg = req.get('serial') or read_config().get('serial', {})
    port = serial_cfg.get('port', 'MOCK')
    try:
        baudrate = int(serial_cfg.get('baudrate', 9600))
    except (ValueError, TypeError):
        baudrate = 9600
    
    if port == 'MOCK':
        return jsonify({'success': True, 'message': 'MOCK serial mode test passed (synthetic hardware).'})
        
    try:
        import serial
        ser = serial.Serial(port=port, baudrate=baudrate, timeout=1.0)
        ser.close()
        return jsonify({'success': True, 'message': f'Serial port {port} opened successfully at {baudrate} bps!'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Serial port {port} test error: {str(e)}'})

@socketio.on('connect')
def handle_connect():
    """Fires when browser client opens or refreshes the page."""
    pid, mode = get_running_process()
    is_active = pid is not None
    cfg = read_config()
    port = cfg.get('serial', {}).get('port', 'N/A')
    
    # 1. Update client running status immediately
    emit('status_change', {
        'is_running': is_active,
        'mode': mode or 'mockup',
        'port': port
    })
    
    # 2. Feed last stats if process is active
    if is_active and last_stats:
        emit('stats_update', last_stats)
        
    # 3. Stream historical logs so terminal console is populated
    logs = get_last_logs(50)
    for log_line in logs:
        emit('log_update', {'log': log_line})
        
    # Start tailing if a process is already running
    if is_active:
        start_tailing()

@socketio.on('start_musashi')
def handle_start(data=None):
    """Spawns Musashi III ingestion process in background."""
    with process_lifecycle_lock:
        data = data or {}
        pid, mode = get_running_process()
        if pid is not None:
            emit('log_update', {'log': '[SYSTEM] Warning: Musashi III ingestion process is already running.'})
            return
            
        run_mode = data.get('mode', 'mockup')
        write_desired_state(True, run_mode)
        
        script_path = os.path.join(BASE_DIR, "read_musashi.py")
        
        cmd = [sys.executable, script_path, "--config", CONFIG_PATH]
        if run_mode in ("mockup", "mock"):
            cmd.append("--mock")
            
        try:
            # Clear/truncate old log file session
            with open(LOG_PATH, 'w', encoding='utf-8') as f:
                f.write(f"[SYSTEM] Log session initialized for MUSASHI III mode={run_mode.upper()}\n")
                
            log_file = open(LOG_PATH, 'a', encoding='utf-8')
            
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            
            popen_kwargs = dict(
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )
            if sys.platform != "win32":
                popen_kwargs["close_fds"] = True
                popen_kwargs["start_new_session"] = True
            else:
                popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(cmd, **popen_kwargs)
            log_file.close()
            
            # Persist PID & Mode metadata
            with open(PID_PATH, 'w') as f:
                f.write(str(proc.pid))
            with open(MODE_PATH, 'w') as f:
                f.write(run_mode)
                
            port = read_config().get('serial', {}).get('port', 'N/A')
            # Update sockets immediately
            socketio.emit('status_change', {'is_running': True, 'mode': run_mode, 'port': port})
            socketio.emit('log_update', {'log': f'[SYSTEM] Spawning Musashi III process (PID: {proc.pid}) mode={run_mode.upper()}'})
            
            # Start log tailer thread
            start_tailing()
            
        except Exception as e:
            socketio.emit('log_update', {'log': f'[SYSTEM] Failed to spawn Musashi III process: {e}'})

@socketio.on('stop_musashi')
def handle_stop():
    """Stops the background process by its recorded PID."""
    with process_lifecycle_lock:
        pid, _ = get_running_process()
        port = read_config().get('serial', {}).get('port', 'N/A')
        if pid is None:
            socketio.emit('status_change', {'is_running': False, 'mode': 'mockup', 'port': port})
            emit('log_update', {'log': '[SYSTEM] Warning: Ingestion process is not running. Resetting UI state.'})
            if os.path.exists(PID_PATH):
                try: os.remove(PID_PATH)
                except OSError: pass
            if os.path.exists(MODE_PATH):
                try: os.remove(MODE_PATH)
                except OSError: pass
            return
            
        current_state = read_desired_state()
        target_mode = current_state.get('mode', 'mockup')
        write_desired_state(False, target_mode)
        socketio.emit('log_update', {'log': f'[SYSTEM] Terminating Musashi III process (PID: {pid})...'})
        
        # 1. Stop log tailing thread cleanly
        stop_tail_event.set()
        global tail_thread
        with tail_lock:
            if tail_thread is not None and tail_thread.is_alive():
                if tail_thread != threading.current_thread():
                    tail_thread.join(timeout=2.0)
                tail_thread = None
        
        # 2. Terminate background process
        terminate_pid(pid)
        
        # 3. Clean up metadata files
        if os.path.exists(PID_PATH):
            try: os.remove(PID_PATH)
            except OSError: pass
        if os.path.exists(MODE_PATH):
            try: os.remove(MODE_PATH)
            except OSError: pass
            
        socketio.emit('status_change', {'is_running': False, 'mode': target_mode, 'port': port})
        socketio.emit('log_update', {'log': '[SYSTEM] Musashi III Ingestion process terminated.'})

def init_application():
    """Initial recovery check and auto-start on Web GUI startup."""
    pid, mode = get_running_process()
    if pid is not None:
        print(f"[SYSTEM] Detected active Musashi III process running (PID: {pid}). Re-attaching...")
        start_tailing()
    else:
        cfg = read_config()
        startup_cfg = cfg.get('startup', {})
        auto_start_enabled = startup_cfg.get('auto_start_on_startup', cfg.get('AUTO_START_ON_STARTUP', True))
        desired_state = read_desired_state()
        is_desired_running = desired_state.get('is_running', False)
        
        if auto_start_enabled or is_desired_running:
            target_mode = startup_cfg.get('auto_start_mode', cfg.get('AUTO_START_MODE')) or desired_state.get('mode', 'mockup')
            print(f"[SYSTEM] Startup config auto_start_on_startup is enabled. Auto-starting Musashi III ingestion in MODE={target_mode.upper()}...")
            handle_start({'mode': target_mode})
        else:
            print("[SYSTEM] Startup config auto_start_on_startup is disabled. Awaiting manual start trigger.")

if __name__ == '__main__':
    init_application()
    # Served on Port 8082
    socketio.run(app, host='0.0.0.0', port=8082, debug=False)