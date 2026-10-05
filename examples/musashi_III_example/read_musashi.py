import serial
import serial.tools.list_ports
import time
import re
import json
import os
import sys
import argparse
import logging
import datetime
from database_handler import DatabaseHandler

# Ensure UTF-8 output encoding on Windows consoles to prevent UnicodeEncodeError
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# RS-232C Communication Control Codes (Refer to Page 79)
STX = b'\x02'
ETX = b'\x03'
EOT = b'\x04'
ENQ = b'\x05'
ACK = b'\x06'
CAN = b'\x18'

# Maximum frame size allowed in read_frame to prevent unbounded memory growth
MAX_FRAME_SIZE = 128

# Precompiled regex for DA01 response payload
# Format: P xxxx T xxxxx V xxxx M x N xxxxxxxxxx
# Numeric fields allow space padding (digits or spaces)
DA01_REGEX = re.compile(
    r"^P(?P<pressure>[\d\s]{4})"
    r"T(?P<time>[\d\s]{5})"
    r"V(?P<vacuum>[\d\s]{4})"
    r"M(?P<mode>[\d\s])"
    r"N(?P<name>.{10})$",
    re.DOTALL
)


class MusashiDispenser:
    def __init__(self, port, baudrate=9600, timeout=2.0, init_delay=1.0):
        """
        Initializes serial connection to MUSASHI Super ΣCMII dispenser.
        Communication specifications based on Page 78:
        9600 bps (default), 8 data bits, no parity, 1 stop bit.
        """
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=timeout
        )
        if init_delay > 0:
            time.sleep(init_delay)  # Allow serial port to initialize
        logger.info(f"Connected to MUSASHI Dispenser on {port} at {baudrate} bps.")

    def close(self):
        """Closes the serial connection."""
        if hasattr(self, 'ser') and self.ser and getattr(self.ser, 'is_open', True):
            try:
                self.ser.close()
            except Exception:
                pass
            logger.info("Serial connection closed.")

    def compute_checksum(self, payload):
        """
        Calculates the 2-character hex checksum as specified on Page 83:
        Subtracted from 0 in 8-bit unsigned modulo 256 for all ASCII characters
        in the character count, command, and data payload.
        Accepts both str and bytes/bytearray without throwing TypeError.
        """
        csum = 0
        if isinstance(payload, (bytes, bytearray)):
            for b in payload:
                csum = (csum - b) & 0xFF
        elif isinstance(payload, str):
            for char in payload:
                csum = (csum - ord(char)) & 0xFF
        else:
            raise TypeError(f"Expected str, bytes, or bytearray, got {type(payload).__name__}")
        return f"{csum:02X}"

    def verify_frame_checksum(self, frame_str):
        """
        Verifies the checksum of a frame string (excluding STX and ETX).
        Expected format: [Payload (N chars)][Checksum (2 hex chars)]
        Frame must be at least 6 characters (length + cmd/data + checksum).
        """
        if isinstance(frame_str, (bytes, bytearray)):
            frame_str = frame_str.decode('ascii')

        if len(frame_str) < 6:
            raise ValueError(f"Frame too short to contain checksum: '{frame_str}' (minimum 6 characters required)")
        
        payload = frame_str[:-2]
        recv_checksum = frame_str[-2:].upper()
        calc_checksum = self.compute_checksum(payload)
        
        if recv_checksum != calc_checksum:
            raise ValueError(
                f"Checksum verification failed! Received: '{recv_checksum}', Expected: '{calc_checksum}'"
            )
        return True

    def build_frame(self, command, data=""):
        """
        Builds the command frame matching Page 82 format:
        STX + [2-digit char count] + [Command] + [Data] + [2-digit Checksum] + ETX
        """
        cmd_data = command + data
        # Character count of command + data formatted as 2-digit uppercase hex
        char_count = f"{len(cmd_data):02X}"
        payload = char_count + cmd_data
        checksum = self.compute_checksum(payload)
        
        frame = STX + payload.encode('ascii') + checksum.encode('ascii') + ETX
        return frame

    def read_frame(self, already_read_stx=False):
        """
        Reads a full STX ... ETX frame from the serial buffer.
        Returns the decoded string inside STX and ETX.
        Includes an STX hunting loop bounded by timeout, strict ASCII decoding,
        and maximum frame size enforcement.
        """
        if not already_read_stx:
            stx_found = False
            start_time = time.time()
            timeout_val = getattr(self.ser, 'timeout', 2.0)
            if timeout_val is None or timeout_val <= 0:
                timeout_val = 2.0
            while (time.time() - start_time) <= timeout_val:
                b = self.ser.read(1)
                if not b:
                    break
                if b == STX:
                    stx_found = True
                    break
            if not stx_found:
                raise Exception("Timeout waiting for response frame STX (0x02).")

        frame_bytes = bytearray()
        while True:
            b = self.ser.read(1)
            if not b:
                raise Exception("Timeout while reading the remainder of the frame.")
            if b == ETX:
                break
            frame_bytes.extend(b)
            if len(frame_bytes) > MAX_FRAME_SIZE:
                raise ValueError(f"Frame exceeded maximum allowed size of {MAX_FRAME_SIZE} bytes.")

        try:
            return frame_bytes.decode('ascii')
        except UnicodeDecodeError as e:
            raise ValueError(f"Frame contained non-ASCII bytes: {e}") from e

    def _send_abort_sequence(self):
        """Attempts to send CAN (0x18) + short sleep + EOT (0x04) and reset input buffer."""
        try:
            if hasattr(self, 'ser') and self.ser and getattr(self.ser, 'is_open', True):
                self.ser.write(CAN)
                time.sleep(0.05)
                self.ser.write(EOT)
                if hasattr(self.ser, 'reset_input_buffer'):
                    self.ser.reset_input_buffer()
        except Exception as e:
            logger.debug(f"Failed to send abort sequence: {e}")

    def execute_upload_command(self, command="UL", data="001D01"):
        """
        Executes an Upload type command (UL) using the 10-step Handshake Procedure (Page 81).
        On any exception or failure, attempts abort recovery (CAN + EOT + reset_input_buffer).
        """
        try:
            return self._execute_upload_handshake(command, data)
        except Exception:
            self._send_abort_sequence()
            raise

    def _execute_upload_handshake(self, command="UL", data="001D01"):
        if hasattr(self.ser, 'reset_input_buffer'):
            self.ser.reset_input_buffer()

        # Step 1: PC sends ENQ
        self.ser.write(ENQ)

        # Step 2: Dispenser replies ACK
        resp = self.ser.read(1)
        if resp != ACK:
            raise Exception(f"Handshake failed at Step 2: Expected ACK (0x06), got: {resp!r}")

        # Step 3: PC sends Upload Command
        frame = self.build_frame(command, data)
        self.ser.write(frame)

        # Step 4: Dispenser replies ACK (0x06) or A0 frame (STX 02 A0 2D ETX)
        resp = self.ser.read(1)
        if not resp:
            raise Exception("Timeout waiting for Dispenser response after sending upload command.")

        if resp == STX:
            # Dispenser returned a frame (A0 confirmation or A2 error)
            cmd_resp_str = self.read_frame(already_read_stx=True)
            # Step 4 Error Frame Check: Check if response is A2 error frame BEFORE checksum verification
            if len(cmd_resp_str) >= 4 and cmd_resp_str[2:4] == "A2":
                self.ser.write(CAN)
                time.sleep(0.05)
                self.ser.write(EOT)
                if hasattr(self.ser, 'reset_input_buffer'):
                    self.ser.reset_input_buffer()
                raise Exception(f"Command Error (A2) returned by Dispenser: {cmd_resp_str}")

            self.verify_frame_checksum(cmd_resp_str)
            
            if len(cmd_resp_str) >= 4 and cmd_resp_str[2:4] == "A0":
                # Command accepted with A0 frame! Acknowledge receipt of A0 frame
                self.ser.write(ACK)
            else:
                raise Exception(f"Unexpected response frame in Step 4: {cmd_resp_str}")
        elif resp == ACK:
            # Single byte ACK response, proceed to Step 5
            pass
        else:
            raise Exception(f"Unexpected response byte in Step 4: {resp!r}")

        # Step 5: PC sends EOT
        self.ser.write(EOT)

        # Step 6: Dispenser sends ENQ (0x05) or sends STX data frame directly
        first_byte = self.ser.read(1)
        if not first_byte:
            raise Exception("Timeout waiting for Dispenser upload data response after EOT.")

        if first_byte == ENQ:
            # Step 7: PC replies ACK
            self.ser.write(ACK)

            # Step 8: Dispenser sends Upload Data frame starting with STX
            data_frame_str = self.read_frame(already_read_stx=False)
        elif first_byte == STX:
            # Dispenser sent data frame starting with STX directly after EOT
            data_frame_str = self.read_frame(already_read_stx=True)
        else:
            raise Exception(f"Handshake failed: Expected ENQ (0x05) or STX (0x02), got: {first_byte!r}")

        # Check if returned payload indicates command error A2 before checksum
        if len(data_frame_str) >= 4 and data_frame_str[2:4] == "A2":
            self.ser.write(CAN)
            time.sleep(0.05)
            self.ser.write(EOT)
            if hasattr(self.ser, 'reset_input_buffer'):
                self.ser.reset_input_buffer()
            raise Exception(f"Command Error (A2) returned by Dispenser: {data_frame_str}")

        # Verify checksum of received data frame
        self.verify_frame_checksum(data_frame_str)

        # Step 9: PC replies ACK
        self.ser.write(ACK)

        # Step 10: Dispenser sends EOT without blocking 2s if omitted or timed out
        orig_timeout = getattr(self.ser, 'timeout', 2.0)
        try:
            if hasattr(self.ser, 'timeout'):
                self.ser.timeout = min(orig_timeout, 0.1) if orig_timeout is not None else 0.1
            resp_eot = self.ser.read(1)
            if resp_eot and resp_eot != EOT:
                logger.warning(f"Expected EOT (0x04) at Step 10, got: {resp_eot!r}")
        finally:
            if hasattr(self.ser, 'timeout'):
                self.ser.timeout = orig_timeout

        return data_frame_str

    def parse_da01_parameters(self, frame_str):
        """
        Parses DA01 response payload (Dispense parameters):
        Format: [2-digit hex length] DA01 P xxxx T xxxxx V xxxx M x N xxxxxxxxxx CS
        """
        if len(frame_str) < 6:
            raise ValueError(f"Invalid frame format: '{frame_str}'")

        # Strip checksum (last 2 characters) if frame contains checksum
        # Check if frame without last 2 chars matches DA01 or length-prefixed DA01
        temp = frame_str[:-2]
        if temp.startswith("DA01") or (len(temp) >= 6 and temp[2:].startswith("DA01")):
            payload = temp
        else:
            payload = frame_str

        # Dynamically strip 2-digit hex length prefix if present
        if len(payload) >= 6 and payload[2:].startswith("DA01"):
            try:
                int(payload[:2], 16)
                payload = payload[2:]
            except ValueError:
                pass
            
        if not payload.startswith("DA01"):
            raise ValueError(f"Invalid payload format for DA01: '{frame_str}'")
            
        content = payload[4:]  # strip DA01 command prefix
        
        match = DA01_REGEX.match(content)
        if not match:
            raise ValueError(f"Failed to parse DA01 parameters pattern from: '{content}'")

        groups = match.groupdict()
        
        p_raw = int(groups['pressure'].strip())
        pressure_kpa = round(p_raw * 0.1, 1)  # 0.1 kPa per unit
        
        t_raw = int(groups['time'].strip())
        time_ms = t_raw  # 1 ms per unit
        
        v_raw = int(groups['vacuum'].strip())
        vacuum_kpa = round(v_raw * 0.01, 2)  # 0.01 kPa per unit
        
        mode_code = int(groups['mode'].strip())
        mode_names = {
            0: "Timed",
            1: "Manual",
            2: "Sigma Timed",
            3: "Sigma Manual"
        }
        mode_name = mode_names.get(mode_code, f"Unknown ({mode_code})")
        
        product_name = groups['name'].rstrip(' \t\r\n\x00')

        return {
            "pressure_kpa": pressure_kpa,
            "pressure_raw": p_raw,
            "time_ms": time_ms,
            "time_sec": round(time_ms / 1000.0, 3),
            "vacuum_kpa": vacuum_kpa,
            "mode_code": mode_code,
            "mode_name": mode_name,
            "product_name": product_name,
            "raw_payload": frame_str
        }

    def read_pressure(self, channel=1):
        """
        Reads and extracts the pressure value (in kPa) for a given channel (1 to 100).
        """
        if not (1 <= channel <= 100):
            raise ValueError("Channel must be between 1 and 100.")
            
        channel_str = f"{channel:03d}"  # Format as 3 digits (e.g. 001)
        data_param = f"{channel_str}D01"
        
        resp_frame = self.execute_upload_command("UL", data_param)
        parsed = self.parse_da01_parameters(resp_frame)
        parsed["channel"] = channel
        return parsed

    def read_dispense_parameters(self, channel=1):
        """Alias for read_pressure returning full dispensing parameters for a channel."""
        return self.read_pressure(channel=channel)


class MockMusashiDispenser:
    """Mock/Synthetic Musashi dispenser for driver-free & offline hardware testing."""
    def __init__(self, port="MOCK", baudrate=9600, timeout=2.0, init_delay=0.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        logger.info("Connected to MOCK MUSASHI Dispenser (Synthetic Simulation Mode).")

    def close(self):
        """Closes mock connection."""
        logger.info("Mock serial connection closed.")

    def compute_checksum(self, payload):
        """Calculates 2-character hex checksum matching real dispenser."""
        csum = 0
        if isinstance(payload, (bytes, bytearray)):
            for b in payload:
                csum = (csum - b) & 0xFF
        elif isinstance(payload, str):
            for char in payload:
                csum = (csum - ord(char)) & 0xFF
        else:
            raise TypeError(f"Expected str, bytes, or bytearray, got {type(payload).__name__}")
        return f"{csum:02X}"

    def verify_frame_checksum(self, frame_str):
        """Verifies frame checksum matching real dispenser."""
        if isinstance(frame_str, (bytes, bytearray)):
            frame_str = frame_str.decode('ascii')
        if len(frame_str) < 6:
            raise ValueError(f"Frame too short to contain checksum: '{frame_str}' (minimum 6 characters required)")
        payload = frame_str[:-2]
        recv_checksum = frame_str[-2:].upper()
        calc_checksum = self.compute_checksum(payload)
        if recv_checksum != calc_checksum:
            raise ValueError(
                f"Checksum verification failed! Received: '{recv_checksum}', Expected: '{calc_checksum}'"
            )
        return True

    def build_frame(self, command, data=""):
        """Builds command frame matching real dispenser."""
        cmd_data = command + data
        char_count = f"{len(cmd_data):02X}"
        payload = char_count + cmd_data
        checksum = self.compute_checksum(payload)
        return STX + payload.encode('ascii') + checksum.encode('ascii') + ETX

    def read_frame(self, already_read_stx=False):
        """Stub method for read_frame."""
        return "02A02D"

    def execute_upload_command(self, command="UL", data="001D01"):
        """Stub method for execute_upload_command returning a valid DA01 frame string."""
        p_raw = 500
        time_ms = 250
        v_raw = 50
        prod_name_10 = "PROD_MOCK "
        cmd_data = f"DA01P{p_raw:04d}T{time_ms:05d}V{v_raw:04d}M2N{prod_name_10}"
        length_prefix = f"{len(cmd_data):02X}"
        payload = length_prefix + cmd_data
        checksum = self.compute_checksum(payload)
        return payload + checksum

    def parse_da01_parameters(self, frame_str):
        """Parses DA01 parameters matching real dispenser."""
        return MusashiDispenser.parse_da01_parameters(self, frame_str)

    def read_pressure(self, channel=1):
        """Reads and extracts pressure value for given channel (1 to 100)."""
        if not (1 <= channel <= 100):
            raise ValueError("Channel must be between 1 and 100.")

        import random
        p_raw = random.randint(480, 520)
        time_ms = random.randint(240, 260)
        v_raw = random.randint(45, 55)
        
        pressure_kpa = round(p_raw * 0.1, 1)
        vacuum_kpa = round(v_raw * 0.01, 2)
        
        prod_name_10 = "PROD_MOCK "  # Exact 10 characters
        cmd_data = f"DA01P{p_raw:04d}T{time_ms:05d}V{v_raw:04d}M2N{prod_name_10}"
        length_prefix = f"{len(cmd_data):02X}"
        payload = length_prefix + cmd_data
        checksum = self.compute_checksum(payload)
        raw_payload = payload + checksum

        return {
            "channel": channel,
            "pressure_kpa": pressure_kpa,
            "pressure_raw": p_raw,
            "time_ms": time_ms,
            "time_sec": round(time_ms / 1000.0, 3),
            "vacuum_kpa": vacuum_kpa,
            "mode_code": 2,
            "mode_name": "Sigma Timed",
            "product_name": prod_name_10.rstrip(' \t\r\n\x00'),
            "raw_payload": raw_payload
        }

    def read_dispense_parameters(self, channel=1):
        return self.read_pressure(channel=channel)


def resolve_serial_port(requested_port):
    """
    Resolves serial port path for cross-platform compatibility (Windows vs macOS vs Linux).
    - On Windows: only auto-selects if requested_port is AUTO or a /dev/ path. Never hijacks
      a requested COM port.
    - On Linux: if requested port is a macOS /dev/cu.usbserial path or AUTO or COM port,
      resolves to detected /dev/ttyUSB* or /dev/ttyACM* port.
    """
    if not requested_port:
        requested_port = "AUTO"

    try:
        available_ports = [p.device for p in serial.tools.list_ports.comports()]
    except Exception:
        available_ports = []

    is_windows = sys.platform == "win32" or os.name == "nt"
    is_linux = sys.platform.startswith("linux")

    if is_windows:
        # On Windows: only auto-select port if requested_port is AUTO or /dev/ path.
        # Do NOT hijack another COM port if a specific COM was requested.
        if requested_port.upper() == "AUTO" or requested_port.startswith("/dev/"):
            if available_ports:
                chosen = available_ports[0]
                logger.warning(
                    f"Configured port '{requested_port}' requires auto-detection on Windows. "
                    f"Auto-selected detected port '{chosen}' (Available: {available_ports})"
                )
                return chosen
            else:
                logger.warning(
                    f"Configured port '{requested_port}' requires auto-detection on Windows, but no COM ports detected. "
                    f"Defaulting to 'COM1'."
                )
                return "COM1"
        return requested_port

    if is_linux:
        # On Linux: if requested port is a macOS /dev/cu.usbserial path or AUTO or COM port,
        # resolve to detected /dev/ttyUSB* or /dev/ttyACM* port.
        if requested_port.startswith("/dev/cu.") or requested_port.upper() == "AUTO" or requested_port.startswith("COM"):
            matching_ports = [p for p in available_ports if "/dev/ttyUSB" in p or "/dev/ttyACM" in p or "ttyUSB" in p or "ttyACM" in p]
            if matching_ports:
                chosen = matching_ports[0]
                logger.warning(
                    f"Port '{requested_port}' resolved on Linux to detected port '{chosen}'."
                )
                return chosen
            elif available_ports:
                chosen = available_ports[0]
                logger.warning(
                    f"Port '{requested_port}' resolved on Linux to detected port '{chosen}'."
                )
                return chosen
            else:
                default_linux = "/dev/ttyUSB0"
                logger.warning(
                    f"Port '{requested_port}' invalid on Linux and no ports detected. Defaulting to '{default_linux}'."
                )
                return default_linux
        return requested_port

    # macOS or other POSIX
    if requested_port.startswith("COM") or requested_port.upper() == "AUTO":
        if available_ports:
            chosen = available_ports[0]
            logger.warning(
                f"Configured port '{requested_port}' invalid on {sys.platform}. "
                f"Auto-selected detected port '{chosen}' (Available: {available_ports})"
            )
            return chosen

    return requested_port


def load_config(config_path="config.json"):
    """Loads configuration from JSON file or returns default parameters."""
    default_port = "COM1" if sys.platform == "win32" else "/dev/cu.usbserial-A600bsZD"
    if not os.path.isabs(config_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(base_dir, config_path)
        if os.path.exists(candidate):
            config_path = candidate
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    logger.warning(f"Config file '{config_path}' not found. Falling back to default settings.")
    return {
        "serial": {
            "port": default_port,
            "baudrate": 9600,
            "timeout": 2.0,
            "channel": 1
        },
        "database": {
            "db_type": "sqlite",
            "db_name": "musashi_data.db",
            "table_name": "musashi_telemetry",
            "description": "Database storage for MUSASHI Super Sigma CMII Dispenser telemetry data"
        },
        "acquisition": {
            "interval_time": 5.0,
            "max_retries": 3
        }
    }


def run_ingestion_loop(config_path="config.json", max_iterations=None, override_interval=None, override_channel=None, override_port=None, mock_mode=False):
    """
    Main loop that continuously reads telemetry data from MUSASHI dispenser
    and saves it to the database at a configured interval_time.
    Supports automatic reconnection with exponential backoff if serial connection is lost.
    """
    config = load_config(config_path)
    
    serial_cfg = config.get("serial", {})
    db_cfg = config.get("database", {})
    acq_cfg = config.get("acquisition", {})

    raw_port = override_port if override_port is not None else serial_cfg.get("port", "COM1" if sys.platform == "win32" else "/dev/cu.usbserial-A600bsZD")
    port = "MOCK" if mock_mode else resolve_serial_port(raw_port)
    baudrate = serial_cfg.get("baudrate", 9600)
    timeout = serial_cfg.get("timeout", 2.0)
    channel = override_channel if override_channel is not None else serial_cfg.get("channel", 1)
    
    interval_time = override_interval if override_interval is not None else acq_cfg.get("interval_time", 5.0)

    print("=" * 65)
    print("      MUSASHI Super Sigma CMII Telemetry Ingestion Service      ")
    print("=" * 65)
    print(f"  Mode:          {'MOCK (Synthetic Hardware Simulation)' if mock_mode else 'REAL (Physical Hardware RS-232)'}")
    print(f"  Serial Port:   {port} @ {baudrate} bps")
    print(f"  Channel:       {channel}")
    print(f"  Interval Time: {interval_time} seconds")
    print(f"  DB Type:       {db_cfg.get('db_type', 'sqlite')}")
    print(f"  DB Name:       {db_cfg.get('db_name', 'musashi_data.db')}")
    print(f"  Table Name:    {db_cfg.get('table_name', 'musashi_telemetry')}")
    print(f"  DB Desc:       {db_cfg.get('description', 'N/A')}")
    print("=" * 65)

    dispenser = None
    db_handler = None
    reconnect_delay = 1.0
    max_reconnect_delay = 30.0

    def init_dispenser():
        if mock_mode:
            return MockMusashiDispenser(port="MOCK", baudrate=baudrate, timeout=timeout)
        else:
            resolved = resolve_serial_port(raw_port)
            return MusashiDispenser(port=resolved, baudrate=baudrate, timeout=timeout)

    try:
        try:
            dispenser = init_dispenser()
        except (serial.SerialException, OSError) as err:
            logger.error(f"Initial connection to dispenser failed: {err}. Will retry in ingestion loop.")
            dispenser = None

        db_handler = DatabaseHandler(db_cfg)
        
        iteration = 0
        print(f"\nStarting data collection loop (interval: {interval_time}s). Press Ctrl+C to stop.\n")

        while True:
            if max_iterations is not None and iteration >= max_iterations:
                print(f"\nReached target iterations limit ({max_iterations}). Exiting loop.")
                break

            # Handle reconnection if dispenser is not connected
            if dispenser is None:
                logger.info(f"Attempting to reconnect to dispenser (retry backoff: {reconnect_delay:.1f}s)...")
                try:
                    dispenser = init_dispenser()
                    logger.info("Dispenser connection established.")
                    reconnect_delay = 1.0  # Reset backoff on success
                except (serial.SerialException, OSError) as conn_err:
                    logger.error(f"Reconnection failed: {conn_err}. Retrying in {reconnect_delay:.1f}s...")
                    time.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    continue

            iteration += 1
            timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
            print(f"[{timestamp_str}] [Loop #{iteration}] Reading Channel {channel}...")
            
            try:
                data = dispenser.read_pressure(channel=channel)
                row_id = db_handler.insert_telemetry(data)
                
                print(f"  -> Success! Stored record #{row_id} in database.")
                print(f"     Pressure: {data['pressure_kpa']} kPa | Time: {data['time_ms']} ms | Vacuum: {data['vacuum_kpa']} kPa | Mode: {data['mode_name']} | Product: '{data['product_name']}'")
                print(f"[STATS] polled={iteration} | written={iteration} | db_errors=0 | pressure_kpa={data['pressure_kpa']} | time_ms={data['time_ms']} | vacuum_kpa={data['vacuum_kpa']} | mode={data['mode_name']} | product={data['product_name']}")
                sys.stdout.flush()
            except (serial.SerialException, OSError) as ser_err:
                logger.error(f"Serial connection lost or I/O error: {ser_err}. Closing dispenser and scheduling reconnect...")
                if dispenser:
                    try:
                        dispenser.close()
                    except Exception:
                        pass
                dispenser = None
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                continue
            except Exception as err:
                logger.error(f"Error acquiring or saving data: {err}")
                sys.stdout.flush()
                if not mock_mode and "Handshake failed" in str(err):
                    logger.warning(
                        f"[HINT] No response received from serial port '{port}'.\n"
                        f"       1. Ensure dispenser unit is powered ON and RS-232 cable is connected.\n"
                        f"       2. Verify port name (e.g., --port COM3 or --port COM4).\n"
                        f"       3. To run in driver-free simulation mode, use: python read_musashi.py --mock"
                    )

            if max_iterations is not None and iteration >= max_iterations:
                print(f"\nReached target iterations limit ({max_iterations}). Exiting loop.")
                break

            print(f"  -> Sleeping for {interval_time} seconds...\n")
            time.sleep(interval_time)

    except KeyboardInterrupt:
        print("\n[STOP] Ingestion loop stopped by user (KeyboardInterrupt). Exiting...")
    except Exception as err:
        logger.error(f"Service encountered an error: {err}")
    finally:
        if dispenser:
            try:
                dispenser.close()
            except Exception:
                pass
        if db_handler:
            try:
                db_handler.close()
            except Exception:
                pass
        print("Service shutdown complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MUSASHI Super Sigma CMII Data Ingestion and Database Service")
    parser.add_argument("--config", type=str, default="config.json", help="Path to config.json file")
    parser.add_argument("--interval", type=float, default=None, help="Override interval time in seconds between iterations")
    parser.add_argument("--channel", type=int, default=None, help="Override channel number (1 - 100)")
    parser.add_argument("--port", type=str, default=None, help="Override serial port (e.g. COM3 or /dev/ttyUSB0)")
    parser.add_argument("--mock", action="store_true", help="Run in mock/simulation mode without physical hardware")
    parser.add_argument("--once", action="store_true", help="Run once instead of infinite loop")
    
    args = parser.parse_args()

    max_iter = 1 if args.once else None
    run_ingestion_loop(
        config_path=args.config,
        max_iterations=max_iter,
        override_interval=args.interval,
        override_channel=args.channel,
        override_port=args.port,
        mock_mode=args.mock
    )