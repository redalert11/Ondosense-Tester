
# main_window.py
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QThread
import pyqtgraph as pg
from collections import deque
import serial.tools.list_ports as list_ports
from ondosense.serial_worker import SerialWorker
from ondosense.protocol import *
from widgets.param_table import ParamTable

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OndoSense Monitor + Parameters (Modular v2)")
        self.resize(1280, 820)

        # Top controls
        self.port_cb = QtWidgets.QComboBox()
        self.refresh_btn = QtWidgets.QPushButton("↻")
        self.baud_sb = QtWidgets.QSpinBox(); self.baud_sb.setRange(9600, 921600); self.baud_sb.setValue(19200); self.baud_sb.setSingleStep(9600)
        self.rate_ds = QtWidgets.QDoubleSpinBox(); self.rate_ds.setRange(0.5, 200); self.rate_ds.setValue(10.0); self.rate_ds.setSuffix(" Hz")
        self.timeout_ds = QtWidgets.QDoubleSpinBox(); self.timeout_ds.setRange(0.05, 5.0); self.timeout_ds.setValue(0.5); self.timeout_ds.setSuffix(" s")
        self.rts_chk = QtWidgets.QCheckBox("RTS drives DE/RE")
        self.inv_chk = QtWidgets.QCheckBox("DE active-LOW")
        self.auto_sel_chk = QtWidgets.QCheckBox("Write selector automatically"); self.auto_sel_chk.setChecked(True)
        self.auto_tab_chk = QtWidgets.QCheckBox("Auto-switch to incoming tab"); self.auto_tab_chk.setChecked(False)
        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.disconnect_btn = QtWidgets.QPushButton("Disconnect"); self.disconnect_btn.setEnabled(False)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Port:")); top.addWidget(self.port_cb); top.addWidget(self.refresh_btn)
        top.addSpacing(8)
        top.addWidget(QtWidgets.QLabel("PC Baud:")); top.addWidget(self.baud_sb)
        top.addWidget(QtWidgets.QLabel("Rate:")); top.addWidget(self.rate_ds)
        top.addWidget(QtWidgets.QLabel("Timeout:")); top.addWidget(self.timeout_ds)
        top.addSpacing(8)
        top.addWidget(self.rts_chk); top.addWidget(self.inv_chk); top.addWidget(self.auto_sel_chk); top.addWidget(self.auto_tab_chk)
        top.addStretch(1)
        top.addWidget(self.connect_btn); top.addWidget(self.disconnect_btn)

        # Tabs (monitor + parameters)
        self.tabs = QtWidgets.QTabWidget()
        self._build_monitor_tabs()

        self.param_tab = ParamTable()
        self.tabs.addTab(self.param_tab, "Parameters")
        self.param_tab.setEnabled(False)  # until connected

        # Log
        self.status_log = QtWidgets.QPlainTextEdit(); self.status_log.setReadOnly(True)

        root = QtWidgets.QVBoxLayout()
        root.addLayout(top)
        root.addWidget(self.tabs, 1)
        root.addWidget(QtWidgets.QLabel("Log"))
        root.addWidget(self.status_log)  # no stretch factor
        # (optional, to ensure the plots get the extra space)
        root.setStretch(root.indexOf(self.tabs), 1)
        w = QtWidgets.QWidget(); w.setLayout(root)
        self.setCentralWidget(w)

        # Thread / worker
        self.thread = QThread(self)
        self.worker = SerialWorker()
        self.worker.moveToThread(self.thread)

        # Connect top controls
        self.refresh_btn.clicked.connect(self.populate_ports)
        self.connect_btn.clicked.connect(self.on_connect)
        self.disconnect_btn.clicked.connect(self.on_disconnect)
        self.rate_ds.valueChanged.connect(lambda v: self.worker.set_rate(float(v)))
        self.timeout_ds.valueChanged.connect(lambda v: self.worker.set_timeout(float(v)))
        self.rts_chk.toggled.connect(lambda checked: self.worker.set_rts_options(checked, self.inv_chk.isChecked()))
        self.inv_chk.toggled.connect(lambda checked: self.worker.set_rts_options(self.rts_chk.isChecked(), checked))
        self.auto_sel_chk.toggled.connect(self.on_auto_selector_toggled)
        self.thread.started.connect(self.worker.start)

        # Parameter panel signals
        self.param_tab.request_read.connect(self.worker.read_param)
        self.param_tab.request_read_min.connect(self.worker.read_min)
        self.param_tab.request_read_max.connect(self.worker.read_max)
        self.param_tab.request_write.connect(self.worker.write_param)
        self.param_tab.request_save.connect(self.worker.save_params)
        self.param_tab.request_autos_amp.connect(self.worker.autoset_amplifier)
        self.param_tab.request_bg_cal.connect(self.worker.bg_cal)
        self.param_tab.request_bg_remove.connect(self.worker.bg_remove)
        self.param_tab.request_restart_hp.connect(self.worker.restart_hp)
        self.param_tab.request_factory.connect(self.worker.factory_reset)
        # log UI clicks so you can see the button works
        self.param_tab.ui_event.connect(self.on_status)

        # Worker → UI
        self.worker.connected.connect(self.on_connected)
        self.worker.statusmsg.connect(self.on_status)
        self.worker.errored.connect(self.on_error)
        # Param feedback
        self.worker.param_read.connect(self.on_param_read)
        self.worker.param_limits.connect(self.on_param_limits)
        self.worker.param_write.connect(self.on_param_write)
        # Measurement data
        self.worker.distance.connect(self.on_distance)
        self.worker.distance_list.connect(self.on_dlist)
        self.worker.spectrum.connect(self.on_spectrum)
        self.worker.iq.connect(self.on_iq)
        self.worker.peak_list.connect(self.on_peak_list)
        self.worker.peak.connect(self.on_peak)
        self.worker.meas_count.connect(self.on_meas_count)
        self.worker.temperature.connect(self.on_temp)
        self.worker.high_prec.connect(self.on_high_prec)

        self.populate_ports()

    # -------- Monitor tabs --------
    def _build_monitor_tabs(self):
        self.tab_dist = QtWidgets.QWidget()
        self.dist_plot = pg.PlotWidget(title="Distance (m)"); self.dist_plot.showGrid(x=True, y=True, alpha=0.2)
        self.dist_curve = self.dist_plot.plot(pen=pg.mkPen(width=2))
        self.dist_series = deque(maxlen=800); self.dist_idx = 0
        QtWidgets.QVBoxLayout(self.tab_dist).addWidget(self.dist_plot)
        self.tabs.addTab(self.tab_dist, "Distance")

        self.tab_dlist = QtWidgets.QWidget()
        self.dlist_plot = pg.PlotWidget(title="Distance list (m)"); self.dlist_plot.showGrid(x=True, y=True, alpha=0.2)
        self.dlist_curve = self.dlist_plot.plot(stepMode=False, pen=None, symbol='o', symbolSize=6)
        QtWidgets.QVBoxLayout(self.tab_dlist).addWidget(self.dlist_plot)
        self.tabs.addTab(self.tab_dlist, "Distance list")

        self.tab_spec = QtWidgets.QWidget()
        self.spec_plot = pg.PlotWidget(title="Spectrum"); self.spec_plot.showGrid(x=True, y=True, alpha=0.2)
        self.spec_curve = self.spec_plot.plot(pen=pg.mkPen(width=2))
        self.thr_curve  = self.spec_plot.plot(pen=pg.mkPen(width=1, style=QtCore.Qt.PenStyle.DotLine))
        self.spec_meta = QtWidgets.QLabel("")
        lay = QtWidgets.QVBoxLayout(self.tab_spec); lay.addWidget(self.spec_plot); lay.addWidget(self.spec_meta)
        self.tabs.addTab(self.tab_spec, "Spectrum")

        self.tab_iq = QtWidgets.QWidget()
        self.iq_plot = pg.PlotWidget(title="IQ"); self.iq_plot.showGrid(x=True, y=True, alpha=0.2)
        self.i_curve = self.iq_plot.plot(pen=pg.mkPen(width=2))
        self.q_curve = self.iq_plot.plot(pen=pg.mkPen(width=2))
        QtWidgets.QVBoxLayout(self.tab_iq).addWidget(self.iq_plot)
        self.tabs.addTab(self.tab_iq, "IQ")

        self.tab_peaks = QtWidgets.QWidget()
        self.peaks_plot = pg.PlotWidget(title="Peaks"); self.peaks_plot.showGrid(x=True, y=True, alpha=0.2)
        self.peaks_scatter = pg.ScatterPlotItem(size=7); self.peaks_plot.addItem(self.peaks_scatter)
        QtWidgets.QVBoxLayout(self.tab_peaks).addWidget(self.peaks_plot)
        self.tabs.addTab(self.tab_peaks, "Peaks")

        self.tab_sys = QtWidgets.QWidget()
        self.temp_plot = pg.PlotWidget(title="Temperature (°C)"); self.temp_plot.showGrid(x=True, y=True, alpha=0.2)
        self.temp_curve = self.temp_plot.plot(pen=pg.mkPen(width=2))
        self.temp_series = deque(maxlen=800); self.temp_idx = 0
        self.hp_plot = pg.PlotWidget(title="High-precision distance (m)"); self.hp_plot.showGrid(x=True, y=True, alpha=0.2)
        self.hp_curve = self.hp_plot.plot(pen=pg.mkPen(width=2))
        self.hp_series = deque(maxlen=800); self.hp_idx = 0
        self.mc_label = QtWidgets.QLabel("Meas count: —")
        l = QtWidgets.QVBoxLayout(self.tab_sys)
        l.addWidget(self.temp_plot); l.addWidget(self.hp_plot); l.addWidget(self.mc_label)
        self.tabs.addTab(self.tab_sys, "System")

    # -------- Connect / status --------
    def populate_ports(self):
        self.port_cb.clear()
        ports = [p.device for p in list_ports.comports()]
        self.port_cb.addItems(ports or ["COM3"])

    def on_connect(self):
        cfg = dict(
            port=self.port_cb.currentText(),
            baud=int(self.baud_sb.value()),
            timeout=float(self.timeout_ds.value()),
            rate_hz=float(self.rate_ds.value()),
            rts_de=self.rts_chk.isChecked(),
            de_active_low=self.inv_chk.isChecked(),
            selector=SEL_DISTANCE,  # start simple
            auto_write_selector=self.auto_sel_chk.isChecked(),
            pre=0.003, post=0.003,
        )
        self.worker.configure(cfg)
        self.thread.start()

    def on_disconnect(self):
        self.worker.stop()
        self.thread.quit()
        self.thread.wait(2000)

    def on_connected(self, ok: bool, msg: str):
        self.status_log.appendPlainText(msg)
        self.connect_btn.setEnabled(not ok)
        self.disconnect_btn.setEnabled(ok)
        self.port_cb.setEnabled(not ok)
        self.refresh_btn.setEnabled(not ok)
        self.baud_sb.setEnabled(not ok)
        self.param_tab.setEnabled(ok)
        if not ok:
            self._reset_plots()

    def on_auto_selector_toggled(self, checked: bool):
        if checked and self.disconnect_btn.isEnabled():
            self.worker.set_selector(self.worker.cfg.get("selector", SEL_DISTANCE))

    def _reset_plots(self):
        self.dist_series.clear(); self.dist_idx = 0; self.dist_curve.setData([])
        self.dlist_curve.setData([], [])
        self.spec_curve.setData([], []); self.thr_curve.setData([], []); self.spec_meta.setText("")
        self.i_curve.setData([], []); self.q_curve.setData([], [])
        self.peaks_scatter.setData([], [])
        self.temp_series.clear(); self.temp_idx = 0; self.temp_curve.setData([])
        self.hp_series.clear(); self.hp_idx = 0; self.hp_curve.setData([]); self.mc_label.setText("Meas count: —")

    # -------- Parameter callbacks --------
    def on_param_read(self, pid: int, val: int):
        self.param_tab.set_value(pid, val)
        self.status_log.appendPlainText(f"Read 0x{pid:02X} = {val}")

    def on_param_limits(self, pid: int, mn, mx):
        self.param_tab.set_limits(pid, mn=mn, mx=mx)
        if mn is not None: self.status_log.appendPlainText(f"Min 0x{pid:02X} = {mn}")
        if mx is not None: self.status_log.appendPlainText(f"Max 0x{pid:02X} = {mx}")

    def on_param_write(self, pid: int, ok: bool, status: int):
        STATUS_TEXT = {
            0x01: "Success",
            0x02: "Success (weak)",
            0xFF: "Error",
            0xFE: "Unknown command",
            0xFD: "Unknown parameter",
            0xFC: "Range error",
            0xFB: "Forbidden",
            0xFA: "No target",
            0xF9: "Target lost (HP)",
            0xF8: "Error in distance calculation module"
        }
        desc = STATUS_TEXT.get(status, f"0x{status:02X}")
        self.status_log.appendPlainText(f"Write 0x{pid:02X} -> {'OK' if ok else f'FAIL ({desc})'}")

    # -------- Measurement handlers --------
    def maybe_switch(self, widget):
        if self.auto_tab_chk.isChecked():
            self.tabs.setCurrentWidget(widget)

    def on_status(self, msg: str): self.status_log.appendPlainText(msg)
    def on_error(self, err: str): self.status_log.appendPlainText(f"ERROR: {err}"); self.on_disconnect()

    def on_distance(self, meters: float):
        self.dist_series.append((self.dist_idx, meters)); self.dist_idx += 1
        xs, ys = zip(*self.dist_series) if self.dist_series else ([], [])
        self.dist_curve.setData(xs, ys); self.maybe_switch(self.tab_dist)

    def on_dlist(self, vals_m: list):
        xs = list(range(1, len(vals_m)+1))
        self.dlist_curve.setData(xs, vals_m); self.maybe_switch(self.tab_dlist)

    def on_spectrum(self, d: object):
        self.spec_curve.setData(d['freq'], d['mag'])
        self.thr_curve.setData(d['freq'], d['thr'])
        m = d['meta']; self.spec_meta.setText(f"bins={m['count']} maxHz={m['maxHz']} dHz={m['dHz']} ampl={m['ampl']}")
        self.maybe_switch(self.tab_spec)

    def on_iq(self, d: object):
        I = d["I"]; Q = d["Q"]
        self.i_curve.setData(list(range(len(I))), I)
        self.q_curve.setData(list(range(len(Q))), Q)
        self.maybe_switch(self.tab_iq)

    def on_peak_list(self, d: object):
        spots = [{'pos': (d["freq"][i], d["amp"][i])} for i in range(len(d["freq"]))]
        self.peaks_scatter.setData(spots); self.maybe_switch(self.tab_peaks)

    def on_peak(self, d: object):
        self.peaks_scatter.setData([{'pos': (d["freq"], d["amp"])}]); self.maybe_switch(self.tab_peaks)

    def on_meas_count(self, c: int):
        self.mc_label.setText(f"Meas count: {c}"); self.maybe_switch(self.tab_sys)

    def on_temp(self, t_c: float):
        self.temp_series.append((self.temp_idx, t_c)); self.temp_idx += 1
        xs, ys = zip(*self.temp_series) if self.temp_series else ([], [])
        self.temp_curve.setData(xs, ys); self.maybe_switch(self.tab_sys)

    def on_high_prec(self, d: object):
        self.hp_series.append((self.hp_idx, d["d_m"])); self.hp_idx += 1
        xs, ys = zip(*self.hp_series) if self.hp_series else ([], [])
        self.hp_curve.setData(xs, ys)
        self.status_log.appendPlainText(f"HP lost={d['lost']}"); self.maybe_switch(self.tab_sys)
