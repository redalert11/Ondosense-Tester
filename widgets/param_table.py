
# widgets/param_table.py
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import pyqtSignal
from dataclasses import dataclass
from ondosense.protocol import *

@dataclass
class ParamDef:
    pid: int
    name: str
    unit: str = ""
    note: str = ""
    ro: bool = False

PARAMS = [
    ParamDef(PARAM_SN,            "Serial number",              ro=True),
    ParamDef(PARAM_SELECTOR,      "Result Data Selector",       note="Bitmask (IQ=1,Spectrum=2,PeakList=4,Peak=8,Distance=16,DistList=64,MeasCnt=128,Temp=256,HP=512)"),
    ParamDef(PARAM_MEAS_RATE,     "Measurement rate",           "Hz"),
    ParamDef(PARAM_MIN_DIST,      "Minimal distance",           "mm"),
    ParamDef(PARAM_MAX_DIST,      "Maximal distance",           "mm"),
    ParamDef(PARAM_INT_RAW,       "Integrations (raw)"),
    ParamDef(PARAM_INT_SPEC,      "Integrations (spectrum)"),
    ParamDef(PARAM_PROFILE,       "Radar profile",              "", "2:LR fast, 3:Close, 5:LR slow, 16:Max accuracy"),
    ParamDef(PARAM_BAUD,          "Baud rate",                  "baud", "PC will reopen at new baud"),
    ParamDef(PARAM_HP_THRESH,     "HP distance threshold",      "1/(2λ)"),
    ParamDef(PARAM_HP_TIMEOUT,    "HP timeout",                 "ms"),
    ParamDef(PARAM_PREAMP_Q,      "Pre-amp gain Q"),
    ParamDef(PARAM_PREAMP_I,      "Pre-amp gain I"),
    ParamDef(PARAM_ADCG_Q,        "ADC gain Q"),
    ParamDef(PARAM_ADCG_I,        "ADC gain I"),
    ParamDef(PARAM_RX_DELAY,      "RX delay",                   "µs"),
    ParamDef(PARAM_THRESH_SENS,   "Threshold sensitivity"),
    ParamDef(PARAM_THRESH_OFFSET, "Threshold offset"),
    ParamDef(PARAM_DIST_OFFSET,   "Distance offset",            "mm"),
    ParamDef(PARAM_EMA_MS,        "EMA time",                   "ms"),
    ParamDef(PARAM_OUTLIER_TMAX,  "Outlier max time",           "ms"),
    ParamDef(PARAM_OUTLIER_DMAX,  "Outlier max distance"),
    ParamDef(PARAM_OUTLIER_VMAX,  "Outlier max speed",          "µm/s"),
    ParamDef(PARAM_PEAK_SORT,     "Peak sorting",               "", "0:Dist,1:Amp,2:NormAmp,3:Dist rev,4:Amp rev,5:NormAmp rev"),
    ParamDef(PARAM_PEAK_INDEX,    "Peak index"),
    ParamDef(PARAM_SW1_EN,        "SW Out1 enabled"),
    ParamDef(PARAM_SW2_EN,        "SW Out2 enabled"),
    ParamDef(PARAM_SW3_EN,        "SW Out3 enabled"),
    ParamDef(PARAM_SW1_POL,       "SW Out1 polarity"),
    ParamDef(PARAM_SW2_POL,       "SW Out2 polarity"),
    ParamDef(PARAM_SW3_POL,       "SW Out3 polarity"),
    ParamDef(PARAM_IO1_SEL1,      "SW Out1 selection IO1"),
    ParamDef(PARAM_IO1_SEL2,      "SW Out2 selection IO1"),
    ParamDef(PARAM_IO1_SEL3,      "SW Out3 selection IO1"),
    ParamDef(PARAM_CL_MIN,        "Current loop min dist",      "mm"),
    ParamDef(PARAM_CL_MAX,        "Current loop max dist",      "mm"),
    ParamDef(PARAM_CL_ERRMODE,    "Current loop error mode",    "", "0:Low(3.6mA) 1:Preserve"),
]

class ParamTable(QtWidgets.QWidget):
    # FIX: signals must come from QtCore, not QtWidgets
    request_read      = pyqtSignal(int)
    request_read_min  = pyqtSignal(int)
    request_read_max  = pyqtSignal(int)
    request_write     = pyqtSignal(int, int)
    request_save      = pyqtSignal()
    request_autos_amp = pyqtSignal()
    request_bg_cal    = pyqtSignal()
    request_bg_remove = pyqtSignal()
    request_restart_hp= pyqtSignal()
    request_factory   = pyqtSignal()
    ui_event          = pyqtSignal(str)  # for logging clicks

    def __init__(self):
        super().__init__()
        self.table = QtWidgets.QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Sel", "Name", "PID", "Min", "Max", "Value", "Unit", "Note"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked |
            QtWidgets.QAbstractItemView.EditTrigger.SelectedClicked |
            QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
        )

        self.btn_read_sel = QtWidgets.QPushButton("Read Selected")
        self.btn_read_all = QtWidgets.QPushButton("Read All")
        self.btn_limits   = QtWidgets.QPushButton("Read Min/Max (All)")
        self.btn_write_sel= QtWidgets.QPushButton("Write Selected")
        self.btn_save     = QtWidgets.QPushButton("Save (0x0F)")
        self.btn_factory  = QtWidgets.QPushButton("Factory Reset")
        self.btn_autoamp  = QtWidgets.QPushButton("Autoset Amplifier")
        self.btn_bgcal    = QtWidgets.QPushButton("Background Cal")
        self.btn_bgrm     = QtWidgets.QPushButton("Remove Background")
        self.btn_restarthp= QtWidgets.QPushButton("Restart HP")

        grid = QtWidgets.QGridLayout(self)
        grid.addWidget(self.table, 0, 0, 1, 8)
        grid.addWidget(self.btn_read_sel, 1,0)
        grid.addWidget(self.btn_read_all, 1,1)
        grid.addWidget(self.btn_limits,   1,2)
        grid.addWidget(self.btn_write_sel,1,3)
        grid.addWidget(self.btn_save,     1,4)
        grid.addWidget(self.btn_factory,  1,5)
        grid.addWidget(self.btn_autoamp,  1,6)
        grid.addWidget(self.btn_bgcal,    2,6)
        grid.addWidget(self.btn_bgrm,     2,5)
        grid.addWidget(self.btn_restarthp,2,4)

        self._populate_rows()

        # Wire buttons + debug ui_event for visible feedback
        self.btn_read_sel.clicked.connect(lambda: self._emit("Read Selected clicked") or self._read_selected())
        self.btn_read_all.clicked.connect(lambda: self._emit("Read All clicked") or self._read_all())
        self.btn_limits.clicked.connect(lambda: self._emit("Read Min/Max clicked") or self._read_limits_all())
        self.btn_write_sel.clicked.connect(lambda: self._emit("Write Selected clicked") or self._write_selected())
        self.btn_save.clicked.connect(lambda: self._emit("Save clicked") or self.request_save.emit())
        self.btn_factory.clicked.connect(lambda: self._emit("Factory Reset clicked") or self.request_factory.emit())
        self.btn_autoamp.clicked.connect(lambda: self._emit("Autoset Amplifier clicked") or self.request_autos_amp.emit())
        self.btn_bgcal.clicked.connect(lambda: self._emit("Background Cal clicked") or self.request_bg_cal.emit())
        self.btn_bgrm.clicked.connect(lambda: self._emit("Remove Background clicked") or self.request_bg_remove.emit())
        self.btn_restarthp.clicked.connect(lambda: self._emit("Restart HP clicked") or self.request_restart_hp.emit())

    def _emit(self, msg: str):
        self.ui_event.emit(msg)

    def _populate_rows(self):
        self.table.setRowCount(len(PARAMS))
        for r, p in enumerate(PARAMS):
            chk = QtWidgets.QTableWidgetItem()
            chk.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, chk)

            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(p.name))
            pid_item = QtWidgets.QTableWidgetItem(f"0x{p.pid:02X}")
            pid_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, 2, pid_item)

            for c in (3,4):
                it = QtWidgets.QTableWidgetItem("—")
                it.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(r, c, it)

            val_item = QtWidgets.QTableWidgetItem("")
            if p.ro:
                val_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, 5, val_item)

            unit_item = QtWidgets.QTableWidgetItem(p.unit)
            unit_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, 6, unit_item)

            note_item = QtWidgets.QTableWidgetItem(p.note)
            note_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, 7, note_item)

    def rows_selected(self):
        return [r for r in range(self.table.rowCount()) if self.table.item(r,0).checkState()==QtCore.Qt.CheckState.Checked]

    def pid_at(self, row): return PARAMS[row].pid

    def set_value(self, pid: int, val: int):
        for r, p in enumerate(PARAMS):
            if p.pid == pid:
                self.table.item(r,5).setText(str(val)); break

    def set_limits(self, pid: int, mn=None, mx=None):
        for r, p in enumerate(PARAMS):
            if p.pid == pid:
                if mn is not None: self.table.item(r,3).setText(str(mn))
                if mx is not None: self.table.item(r,4).setText(str(mx))
                break

    def _read_selected(self):
        for r in self.rows_selected():
            self.request_read.emit(self.pid_at(r))

    def _read_all(self):
        for p in PARAMS:
            self.request_read.emit(p.pid)

    def _read_limits_all(self):
        for p in PARAMS:
            self.request_read_min.emit(p.pid)
            self.request_read_max.emit(p.pid)

    def _write_selected(self):
        for r in self.rows_selected():
            p = PARAMS[r]
            if p.ro: continue
            txt = self.table.item(r,5).text().strip()
            if txt in ("", "—"): continue
            try:
                v = int(float(txt))
            except ValueError:
                continue
            self.request_write.emit(p.pid, v)
