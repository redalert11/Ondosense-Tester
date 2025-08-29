
# ondosense/serial_worker.py
from PyQt6 import QtCore
from PyQt6.QtCore import pyqtSignal, QObject, QTimer
import serial, struct, time
from .protocol import *

def read_exact(ser: serial.Serial, n: int, overall_timeout: float) -> bytes:
    end = time.time() + overall_timeout
    out = bytearray()
    while len(out) < n and time.time() < end:
        chunk = ser.read(n - len(out))
        if chunk: out.extend(chunk)
        else: time.sleep(0.001)
    return bytes(out)

class SerialWorker(QObject):
    # connection / status
    connected   = pyqtSignal(bool, str)
    statusmsg   = pyqtSignal(str)
    errored     = pyqtSignal(str)

    # measurement data
    distance    = pyqtSignal(float)
    distance_list = pyqtSignal(list)
    spectrum    = pyqtSignal(object)
    iq          = pyqtSignal(object)
    peak_list   = pyqtSignal(object)
    peak        = pyqtSignal(object)
    meas_count  = pyqtSignal(int)
    temperature = pyqtSignal(float)
    high_prec   = pyqtSignal(object)

    # parameters
    param_read  = pyqtSignal(int, int)           # (pid, value)
    param_limits= pyqtSignal(int, int, int)      # (pid, min, max)
    param_write = pyqtSignal(int, bool, int)     # (pid, ok, status)

    def __init__(self):
        super().__init__()
        self.ser = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_once)
        self.running = False
        self.busy = False  # guard re-entrancy
        self.cfg = {
            "port": "COM3",
            "baud": 19200,
            "timeout": 0.5,
            "rate_hz": 10.0,
            "rts_de": False,
            "de_active_low": False,
            "pre": 0.003, "post": 0.003,
            "selector": SEL_DISTANCE,
            "auto_write_selector": True,
        }

    # ------------- lifecycle -------------
    @QtCore.pyqtSlot(dict)
    def configure(self, cfg: dict):
        self.cfg.update(cfg)

    @QtCore.pyqtSlot()
    def start(self):
        try:
            self._open_serial(self.cfg["baud"])
            if self.cfg["rts_de"]:
                self._set_rts(False)
            if self.cfg["auto_write_selector"]:
                self._write_selector(self.cfg["selector"])
            self.running = True
            self.connected.emit(True, f"Opened {self.cfg['port']} @ {self.cfg['baud']}")
            self._reset_timer()
        except Exception as e:
            self.connected.emit(False, f"Open failed: {e}")

    @QtCore.pyqtSlot()
    def stop(self):
        self.running = False
        try:
            self.timer.stop()
        except Exception:
            pass
        try:
            if self.ser: self.ser.close()
        except Exception:
            pass
        self.connected.emit(False, "Disconnected")

    # ------------- live settings -------------
    @QtCore.pyqtSlot(int)
    def set_selector(self, mask: int):
        self.cfg["selector"] = mask
        if self.cfg["auto_write_selector"] and self.ser:
            self._write_selector(mask)

    @QtCore.pyqtSlot(float)
    def set_rate(self, hz: float):
        self.cfg["rate_hz"] = max(0.5, float(hz))
        self._reset_timer()
        self.statusmsg.emit(f"Rate set to {self.cfg['rate_hz']:.1f} Hz")

    def _reset_timer(self):
        if not self.running: return
        interval_ms = max(int(1000.0 / float(self.cfg["rate_hz"])), 5)
        self.timer.start(interval_ms)

    @QtCore.pyqtSlot(float)
    def set_timeout(self, sec: float):
        self.cfg["timeout"] = max(0.05, float(sec))
        if self.ser: self.ser.timeout = self.cfg["timeout"]
        self.statusmsg.emit(f"Timeout set to {self.cfg['timeout']:.2f} s")

    @QtCore.pyqtSlot(bool, bool)
    def set_rts_options(self, rts_de: bool, active_low: bool):
        self.cfg["rts_de"] = bool(rts_de)
        self.cfg["de_active_low"] = bool(active_low)
        if self.ser and self.cfg["rts_de"]:
            self._set_rts(False)
        self.statusmsg.emit(f"RTS/DE={'on' if rts_de else 'off'}, active-low={'yes' if active_low else 'no'}")

    # ------------- parameter ops -------------
    @QtCore.pyqtSlot(int)
    def read_param(self, pid: int):
        if not self.ser: 
            self.statusmsg.emit("Not connected"); return
        try:
            self.busy = True
            self._pre_tx(); self.ser.reset_input_buffer()
            self.ser.write(bytes([CMD_READ_PARAM, pid])); self.ser.flush()
            self._post_tx()
            st_b = read_exact(self.ser, 1, self.cfg["timeout"])
            if len(st_b)==1 and st_b[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                val_b = read_exact(self.ser, 4, self.cfg["timeout"])
                if len(val_b)==4:
                    v = struct.unpack(">i", val_b)[0]
                    self.param_read.emit(pid, v)
                else:
                    self.statusmsg.emit(f"Read 0x{pid:02X}: short value")
            else:
                self.statusmsg.emit(f"Read 0x{pid:02X}: no status")
        except Exception as e:
            self.statusmsg.emit(f"Read error 0x{pid:02X}: {e}")
        finally:
            self.busy = False

    @QtCore.pyqtSlot(int)
    def read_min(self, pid: int):
        self._read_limit(pid, CMD_READ_MIN, is_min=True)

    @QtCore.pyqtSlot(int)
    def read_max(self, pid: int):
        self._read_limit(pid, CMD_READ_MAX, is_min=False)

    def _read_limit(self, pid: int, cmd: int, is_min: bool):
        if not self.ser: 
            self.statusmsg.emit("Not connected"); return
        try:
            self.busy = True
            self._pre_tx(); self.ser.reset_input_buffer()
            self.ser.write(bytes([cmd, pid])); self.ser.flush()
            self._post_tx()
            st_b = read_exact(self.ser, 1, self.cfg["timeout"])
            if len(st_b)==1 and st_b[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                val_b = read_exact(self.ser, 4, self.cfg["timeout"])
                if len(val_b)==4:
                    v = struct.unpack(">i", val_b)[0]
                    if is_min: self.param_limits.emit(pid, v, None)
                    else:      self.param_limits.emit(pid, None, v)
                else:
                    self.statusmsg.emit(f"Limit 0x{pid:02X}: short")
            else:
                self.statusmsg.emit(f"Limit 0x{pid:02X}: no status")
        except Exception as e:
            self.statusmsg.emit(f"Limit error 0x{pid:02X}: {e}")
        finally:
            self.busy = False

    def _hex(self, data: bytes) -> str:
        return " ".join(f"{b:02X}" for b in data)

    @QtCore.pyqtSlot(int, int)
    def write_param(self, pid: int, value: int):
        if not self.ser:
            self.statusmsg.emit("Not connected"); return
        try:
            self.busy = True
            if pid == PARAM_BAUD:
                self.set_sensor_baud(int(value))
                self.param_write.emit(pid, True, STATUS_SUCCESS); return

            self._pre_tx()
            self.ser.reset_input_buffer()
            frame = bytes([CMD_WRITE_PARAM, pid]) + struct.pack(">i", int(value))
            self.statusmsg.emit(f"TX write 0x{pid:02X} ({len(frame)}): {self._hex(frame)}")
            self.ser.write(frame); self.ser.flush()
            self._post_tx()

            ack = read_exact(self.ser, 1, self.cfg["timeout"])
            self.statusmsg.emit(f"RX ack: {self._hex(ack) if ack else '(none)'}")
            ok = len(ack)==1 and ack[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK)
            self.param_write.emit(pid, ok, ack[0] if ack else -1)
        except Exception as e:
            self.statusmsg.emit(f"Write error 0x{pid:02X}: {e}")
            self.param_write.emit(pid, False, -1)
        finally:
            self.busy = False

    @QtCore.pyqtSlot()
    def save_params(self):
        to = max(self.cfg.get('timeout', 0.5) * 2.0, 1.0)
        self._simple_cmd(CMD_SAVE_PARAMS, "Save params (0x0F)", expect_status=True, timeout_override=to)

    @QtCore.pyqtSlot()
    def autoset_amplifier(self):
        self._simple_cmd(CMD_AUTOS_AMP, "Autoset amplifier (0x07)")

    @QtCore.pyqtSlot()
    def bg_cal(self):
        self._simple_cmd(CMD_BG_CAL, "Background calibration (0x0D)")

    @QtCore.pyqtSlot()
    def bg_remove(self):
        self._simple_cmd(CMD_BG_REMOVE, "Remove background (0x0E)")

    @QtCore.pyqtSlot()
    def restart_hp(self):
        self._simple_cmd(CMD_RESTART_HP, "Restart high-precision (0x19)")

    @QtCore.pyqtSlot()
    def factory_reset(self):
        if not self.ser: 
            self.statusmsg.emit("Not connected"); return
        try:
            self.busy = True
            self._pre_tx(); self.ser.reset_input_buffer()
            self.ser.write(bytes([CMD_FACTORY_RESET]) + b"RESET"); self.ser.flush()
            self._post_tx()
            ack = read_exact(self.ser, 1, self.cfg["timeout"])
            ok = len(ack)==1 and ack[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK)
            self.statusmsg.emit("Factory reset OK" if ok else "Factory reset FAILED")
        except Exception as e:
            self.statusmsg.emit(f"Factory reset error: {e}")
        finally:
            self.busy = False

    @QtCore.pyqtSlot(int)
    def set_sensor_baud(self, new_baud: int):
        if not self.ser:
            self.statusmsg.emit("Not connected"); return
        try:
            self.busy = True
            self._pre_tx(); self.ser.reset_input_buffer()
            self.ser.write(bytes([CMD_WRITE_PARAM, PARAM_BAUD]) + struct.pack(">i", int(new_baud)))
            self.ser.flush()
            self._post_tx()
            ack = read_exact(self.ser, 1, self.cfg["timeout"])
            if not (len(ack)==1 and ack[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK)):
                self.statusmsg.emit("Baud write FAILED"); return
            self._reopen_serial(new_baud)
            self.statusmsg.emit(f"Reopened at {new_baud} baud")
        except Exception as e:
            self.statusmsg.emit(f"Baud change error: {e}")
        finally:
            self.busy = False

    # ------------- simple command helper -------------
    def _simple_cmd(self, cmd: int, label: str = "", expect_status: bool = True, timeout_override: float | None = None):
        if not self.ser:
            self.statusmsg.emit("Not connected"); return
        try:
            self.busy = True
            self._pre_tx()
            self.ser.reset_input_buffer()
            tx = bytes([cmd])
            self.statusmsg.emit(f"TX cmd{f' {label}' if label else ''}: {self._hex(tx)}")
            self.ser.write(tx); self.ser.flush()
            self._post_tx()
            if expect_status:
                ack = read_exact(self.ser, 1, (timeout_override if timeout_override is not None else self.cfg["timeout"]))
                self.statusmsg.emit(f"RX ack: {self._hex(ack) if ack else '(none)'}")
                ok = len(ack)==1 and ack[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK)
                code = f"0x{ack[0]:02X}" if ack else "(no byte)"
                self.statusmsg.emit(f"{label}: {'OK' if ok else 'FAIL (' + code + ')'}")
            else:
                self.statusmsg.emit(f"{label}: sent")
        except Exception as e:
            self.statusmsg.emit(f"{label}: error {e}")
        finally:
            self.busy = False

    # ------------- polling -------------
    @QtCore.pyqtSlot()
    def _poll_once(self):
        if not self.running or self.busy or not self.ser:
            return
        if self.cfg["selector"] == 0:
            return
        try:
            self.busy = True
            self._send_measure()

            def want(bit): return (self.cfg["selector"] & bit) != 0

            # IQ
            if want(SEL_IQ):
                s = read_exact(self.ser, 1, self.cfg["timeout"])
                if len(s)==1 and s[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                    cnt_b = read_exact(self.ser, 2, self.cfg["timeout"])
                    if len(cnt_b)==2:
                        cnt = struct.unpack(">H", cnt_b)[0]
                        raw = read_exact(self.ser, 2*cnt, self.cfg["timeout"])
                        if len(raw)==2*cnt:
                            I = [raw[i] for i in range(0, 2*cnt, 2)]
                            Q = [raw[i] for i in range(1, 2*cnt, 2)]
                            self.iq.emit({"I": I, "Q": Q})

            # Spectrum
            if want(SEL_SPECTRUM):
                s = read_exact(self.ser, 1, self.cfg["timeout"])
                if len(s)==1 and s[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                    cnt_b = read_exact(self.ser, 2, self.cfg["timeout"])
                    hdr = read_exact(self.ser, 12, self.cfg["timeout"])
                    if len(cnt_b)==2 and len(hdr)==12:
                        cnt = struct.unpack(">H", cnt_b)[0]
                        maxHz, dHz, ampl = struct.unpack(">III", hdr)
                        mags = read_exact(self.ser, cnt, self.cfg["timeout"])
                        thrs = read_exact(self.ser, cnt, self.cfg["timeout"])
                        if len(mags)==cnt and len(thrs)==cnt:
                            f0 = maxHz - (cnt - 1)*dHz
                            freq = [f0 + i*dHz for i in range(cnt)]
                            self.spectrum.emit({"freq": freq, "mag": list(mags), "thr": list(thrs),
                                                "meta": {"count": cnt, "maxHz": maxHz, "dHz": dHz, "ampl": ampl}})

            # Peak list
            if want(SEL_PEAK_LIST):
                s = read_exact(self.ser, 1, self.cfg["timeout"])
                if len(s)==1 and s[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                    cntidx = read_exact(self.ser, 2, self.cfg["timeout"])
                    if len(cntidx)==2:
                        c, idx = cntidx[0], cntidx[1]
                        raw = read_exact(self.ser, c*10, self.cfg["timeout"])
                        if len(raw)==c*10:
                            freqs = []; amps = []; off = 0
                            for _ in range(c):
                                f_centi = struct.unpack(">I", raw[off:off+4])[0]; off += 4
                                off += 2
                                amp = struct.unpack(">I", raw[off:off+4])[0]; off += 4
                                freqs.append(f_centi/100.0); amps.append(amp)
                            self.peak_list.emit({"freq": freqs, "amp": amps, "idx": idx})

            # Peak
            if want(SEL_PEAK):
                s = read_exact(self.ser, 1, self.cfg["timeout"])
                if len(s)==1 and s[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                    raw = read_exact(self.ser, 10, self.cfg["timeout"])
                    if len(raw)==10:
                        f_centi = struct.unpack(">I", raw[0:4])[0]
                        amp = struct.unpack(">I", raw[6:10])[0]
                        self.peak.emit({"freq": f_centi/100.0, "amp": amp})

            # Distance list
            if want(SEL_DISTANCE_LIST):
                s = read_exact(self.ser, 1, self.cfg["timeout"])
                if len(s)==1 and s[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                    ci = read_exact(self.ser, 2, self.cfg["timeout"])
                    if len(ci)==2:
                        c = ci[0]
                        vals = []
                        for _ in range(c):
                            d_um_b = read_exact(self.ser, 4, self.cfg["timeout"])
                            if len(d_um_b)!=4: vals = []; break
                            vals.append(struct.unpack(">I", d_um_b)[0] / 1e6)
                        if vals:
                            self.distance_list.emit(vals)

            # Distance
            if want(SEL_DISTANCE):
                s = read_exact(self.ser, 1, self.cfg["timeout"])
                if len(s)==1 and s[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                    d_b = read_exact(self.ser, 4, self.cfg["timeout"])
                    if len(d_b)==4:
                        self.distance.emit(struct.unpack(">I", d_b)[0] / 1e6)

            # Measurement count
            if want(SEL_MEAS_COUNT):
                s = read_exact(self.ser, 1, self.cfg["timeout"])
                if len(s)==1 and s[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                    c_b = read_exact(self.ser, 4, self.cfg["timeout"])
                    if len(c_b)==4:
                        self.meas_count.emit(struct.unpack(">I", c_b)[0])

            # Temperature
            if want(SEL_TEMPERATURE):
                s = read_exact(self.ser, 1, self.cfg["timeout"])
                if len(s)==1 and s[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                    t_b = read_exact(self.ser, 4, self.cfg["timeout"])
                    if len(t_b)==4:
                        t_int = struct.unpack(">h", t_b[0:2])[0] / 100.0
                        self.temperature.emit(t_int)

            # High precision
            if want(SEL_HIGH_PREC):
                s = read_exact(self.ser, 1, self.cfg["timeout"])
                if len(s)==1 and s[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK):
                    hp_b = read_exact(self.ser, 5, self.cfg["timeout"])
                    if len(hp_b)==5:
                        lost = hp_b[0]
                        d_hp = struct.unpack(">i", hp_b[1:5])[0] / 1e6
                        self.high_prec.emit({"d_m": d_hp, "lost": lost})
        except Exception as e:
            self.statusmsg.emit(f"Poll error: {e}")
        finally:
            self.busy = False

    # ------------- helpers -------------
    def _open_serial(self, baud: int):
        self.ser = serial.Serial(
            port=self.cfg["port"], baudrate=int(baud),
            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
            timeout=self.cfg["timeout"], write_timeout=self.cfg["timeout"],
            rtscts=False, dsrdtr=False, xonxoff=False
        )
        self.cfg["baud"] = int(baud)

    def _reopen_serial(self, baud: int):
        try:
            if self.ser: self.ser.close()
        except Exception: pass
        time.sleep(0.1)
        self._open_serial(baud)
        if self.cfg["rts_de"]: self._set_rts(False)

    def _pre_tx(self):
        if self.cfg["rts_de"]:
            self._set_rts(True); time.sleep(self.cfg["pre"])

    def _post_tx(self):
        if self.cfg["rts_de"]:
            self._set_rts(False)
        time.sleep(self.cfg["post"])

    def _set_rts(self, tx: bool):
        if not self.ser: return
        level = (not tx) if self.cfg["de_active_low"] else tx
        self.ser.rts = level

    def _write_selector(self, mask: int) -> bool:
        try:
            self._pre_tx()
            self.ser.reset_input_buffer()
            frame = bytes([CMD_WRITE_PARAM, PARAM_SELECTOR, 0, 0, 0, mask & 0xFF])
            self.statusmsg.emit(f"TX selector ({len(frame)}): {self._hex(frame)}")
            self.ser.write(frame); self.ser.flush()
            self._post_tx()
            ack = read_exact(self.ser, 1, self.cfg["timeout"])
            self.statusmsg.emit(f"RX ack: {self._hex(ack) if ack else '(none)'}")
            ok = len(ack)==1 and ack[0] in (STATUS_SUCCESS, STATUS_SUCCESS_WEAK)
            self.statusmsg.emit(f"Selector -> {mask} {'OK' if ok else 'FAILED'}")
            return ok
        except Exception:
            return False

    def _send_measure(self):
        self._pre_tx()
        self.ser.reset_input_buffer()
        self.ser.write(bytes([CMD_MEASUREMENT])); self.ser.flush()
        self._post_tx()
