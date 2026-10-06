import asyncio
import csv
import json
import math
import os
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QFontDatabase, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QFormLayout, QGridLayout, QLabel, QPushButton, QComboBox,
    QDoubleSpinBox, QGroupBox, QPlainTextEdit, QFileDialog, QMessageBox,
    QCheckBox, QScrollArea, QSplitter)
from bleak import BleakClient, BleakScanner
from protocol import Settings, Lines, RX, TX, check_preflight, telemetry, acknowledgement


class Radio(QObject):
    line = Signal(str)
    devices = Signal(object)
    state = Signal(str)
    failure = Signal(str)
    connected = Signal(bool)

    def __init__(self, loop=None):
        super().__init__()
        self.loop = loop or asyncio.new_event_loop()
        self.client = None
        self.pending = None
        self.operation = None
        self.ready = False
        self.framer = Lines()
        self.write_lock = None
        if loop is None:
            threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def submit(self, coroutine):
        async def guarded():
            try:
                await coroutine
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self.ready = False
                self.failure.emit(str(exc) or type(exc).__name__)
        return asyncio.run_coroutine_threadsafe(guarded(), self.loop)

    async def scan(self):
        devices = await BleakScanner.discover(timeout=5)
        self.devices.emit([(d.name or 'Unnamed device', d.address) for d in devices
                           if (d.name or '').upper().startswith('SUNSEEK')])

    def receive(self, _, data):
        try:
            for line in self.framer.feed(data):
                self.line.emit('RX ' + line)
                if self.pending:
                    command, future = self.pending
                    if not future.done():
                        if line.startswith('ERR,') and not line.startswith('ERR,PAYLOAD'):
                            future.set_exception(RuntimeError(line))
                        elif acknowledgement(command, line):
                            future.set_result(line)
        except Exception as exc:
            self.failure.emit(str(exc))

    def disconnected(self, _):
        self.ready = False
        self.connected.emit(False)
        self.state.emit('DISCONNECTED — physical motion unknown')
        if self.pending and not self.pending[1].done():
            self.pending[1].set_exception(RuntimeError('Bluetooth disconnected'))

    async def connect(self, address):
        if self.client and self.client.is_connected:
            raise ValueError('Disconnect the current spacecraft first.')
        self.framer = Lines()
        self.write_lock = asyncio.Lock()
        self.client = BleakClient(address, disconnected_callback=self.disconnected)
        await self.client.connect()
        await self.client.start_notify(TX, self.receive)
        self.connected.emit(True)
        self.state.emit('CONNECTED — not prepared')
        await self.request('PING')
        for cmd in ['TM_RATE,5', 'TM_STREAM,ALL,ON', 'TM_STREAM,ADCS,ON']:
            await self.request(cmd)
        try:
            line = await self.request('QP_STATUS')
            if not line.startswith('ACK,QP_STATUS,2,'):
                raise ValueError('QP2 required')
            self.line.emit('INFO QP2 firmware detected. PREPARE does not start the wheel.')
        except Exception:
            self.failure.emit('Upload the included QP2 firmware. Telemetry remains available; PREPARE will be blocked.')

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.stop()
            await self.client.disconnect()

    async def write(self, command):
        if not self.client or not self.client.is_connected:
            raise RuntimeError('Connect to a spacecraft first.')
        async with self.write_lock:
            # Keep ATT writes at the minimum supported payload; firmware joins fragments.
            data = (command + '\n').encode()
            for start in range(0, len(data), 20):
                await self.client.write_gatt_char(RX, data[start:start+20], response=True)
        self.line.emit('TX ' + command)

    async def request(self, command):
        if self.pending:
            raise RuntimeError('Another command is awaiting a reply.')
        future = self.loop.create_future()
        self.pending = (command, future)
        try:
            await self.write(command)
            return await asyncio.wait_for(future, timeout=5)
        finally:
            self.pending = None

    async def execute(self, settings=None, run=False):
        if self.operation and not self.operation.done():
            raise RuntimeError('An operation is already in progress.')
        self.operation = asyncio.current_task()
        try:
            if run:
                if not self.ready:
                    raise ValueError('PREPARE must succeed before RUN.')
                check_preflight(await self.request('QP_STATUS'))
                self.ready = False
                self.state.emit('STARTING')
                await self.request('MISSION_START')
                self.state.emit('RUNNING')
            else:
                self.ready = False
                commands = settings.plan()
                self.state.emit('CHECKING')
                # Read-only capability/state query before ANY setup commands.
                check_preflight(await self.request('QP_STATUS'))
                self.state.emit('PREPARING — wheel remains off')
                for cmd in commands:
                    await self.request(cmd)
                self.ready = True
                self.state.emit('READY — press RUN to move')
        finally:
            self.operation = None

    async def stop(self):
        self.ready = False
        if self.operation and not self.operation.done():
            self.operation.cancel()
            try:
                await self.operation
            except asyncio.CancelledError:
                pass
        # Interrupt a pending read-only command so STOP does not wait for its timeout.
        if self.pending:
            pending = self.pending
            self.pending = None
            if not pending[1].done():
                pending[1].set_exception(RuntimeError('Cancelled by STOP'))
            await asyncio.sleep(0)
        await self.request('STOP')
        self.state.emit('STOPPED COMMAND — wait for physical rest')


class RatePlot(QWidget):
    def __init__(self):
        super().__init__()
        self.points = []
        self.setMinimumHeight(160)

    def add(self, value):
        now = time.monotonic()
        self.points.append((now, value))
        self.points = [(t, v) for t, v in self.points if now-t <= 30]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#0b1623'))
        p.setPen(QColor('#92a9bf'))
        p.drawText(12, 20, 'BODY RATE · deg/s · last 30 seconds')
        if not self.points:
            return
        maxv = max(5, max(abs(v) for _, v in self.points) * 1.15)
        top, bottom = 35, self.height()-20
        middle = (top+bottom)/2
        p.setPen(QPen(QColor('#294259'), 1))
        p.drawLine(10, int(middle), self.width()-10, int(middle))
        p.drawText(12, 38, f'+{maxv:.1f}')
        p.drawText(12, self.height()-5, f'-{maxv:.1f}')
        p.setPen(QPen(QColor('#5dd5fa'), 2))
        now = time.monotonic()
        previous = None
        for t, v in self.points:
            point = (int(15+(self.width()-30)*(1-(now-t)/30)),
                     int(middle-v/maxv*(bottom-top)/2))
            if previous:
                p.drawLine(*previous, *point)
            previous = point


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('SunSeek Ground Station — Quiet Prepare 1.0')
        self.resize(1280, 900)
        self.radio = Radio()
        self.is_connected = False
        self.connecting = False
        self.phase = 'DISCONNECTED'
        self.run_start = None
        self.hold_start = None
        self.acquired = None
        self.last_rate = 0
        self.last_error = 0
        self.last_valid = 0
        self.data = {}
        self.records = []
        self.configuration = None
        self.inputs = {}
        self.logs = []
        self.build_ui()
        self.radio.line.connect(self.on_line)
        self.radio.failure.connect(self.on_error)
        self.radio.devices.connect(self.on_devices)
        self.radio.state.connect(self.on_state)
        self.radio.connected.connect(self.on_connected)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(250)

    def button(self, text, action, layout):
        b = QPushButton(text)
        b.clicked.connect(action)
        layout.addWidget(b)
        return b

    def build_ui(self):
        shell = QWidget(); self.setCentralWidget(shell)
        outer = QVBoxLayout(shell)
        title = QLabel('SUNSEEK  /  GROUND STATION')
        title.setStyleSheet('font-size:23px;font-weight:700;color:#ecf5ff')
        outer.addWidget(title)
        outer.addWidget(QLabel('PREPARE checks readiness. RUN starts movement. STOP cancels control.'))
        connection = QHBoxLayout(); outer.addLayout(connection)
        self.devices = QComboBox(); self.devices.setMinimumWidth(340)
        connection.addWidget(self.devices, 1)
        self.scan_button = self.button('Scan Bluetooth', self.scan, connection)
        self.connect_button = self.button('Connect', self.connect_device, connection)
        self.disconnect_button = self.button('Disconnect', lambda: self.radio.submit(self.radio.disconnect()), connection)
        self.status = QLabel('DISCONNECTED'); outer.addWidget(self.status)
        split = QSplitter(); outer.addWidget(split, 1)
        left = QWidget(); left.setMinimumWidth(430); form_box = QVBoxLayout(left)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(left)
        split.addWidget(scroll)
        config = QGroupBox('Target and control'); form_box.addWidget(config)
        form = QFormLayout(config)
        for key, label, options in [('reference','Reference',['MAG','SUN']),('strategy','Wheel strategy',['REACTION','MOMENTUM'])]:
            combo = QComboBox(); combo.addItems(options); self.inputs[key] = combo
            combo.currentTextChanged.connect(self.invalidate)
            form.addRow(label, combo)
        fields = [('target','Target angle (°)',0,359.99,0),('tolerance','Tolerance (°)',0.01,30,3),
                  ('hold','Continuous hold (s)',0,60,2),('kp','Kp',0,20,0.5),('kd','Kd',0,20,1)]
        for f in fields: self.spin(form, *f)
        form.addRow(QLabel('MAG: absolute compass heading. SUN: calibrated light angle.'))
        self.inputs['reference'].currentTextChanged.connect(self.reference_changed)
        profiles = QHBoxLayout(); form_box.addLayout(profiles)
        self.button('Save settings', self.save_settings, profiles)
        self.button('Load settings', self.load_settings, profiles)
        self.momentum = QGroupBox('Momentum profile — use measured rig values')
        form_box.addWidget(self.momentum); mf = QFormLayout(self.momentum)
        for f in [('bias','Nominal bias (%)',0,100,40),('cw_delta','CW delta',1,100,10),
                  ('cw_assist','CW assist (%)',-100,100,40),('cw_ms','CW duration (ms)',0,10000,100),
                  ('ccw_delta','CCW delta',-100,-1,-10),('ccw_assist','CCW assist (%)',-100,100,20),
                  ('ccw_ms','CCW duration (ms)',0,10000,100),('recovery_step','Recovery step (%)',1,100,1),
                  ('recovery_ms','Recovery interval (ms)',10,10000,100),('trigger','Demand trigger',0.1,100,5)]:
            self.spin(mf,*f,integer=f[0]!='trigger')
        self.momentum.setVisible(False)
        self.inputs['strategy'].currentTextChanged.connect(lambda x:self.momentum.setVisible(x=='MOMENTUM'))
        self.at_rest = QCheckBox('Body and wheel are physically stationary')
        self.at_rest.toggled.connect(lambda _:self.refresh()); form_box.addWidget(self.at_rest)
        self.profile_verified = QCheckBox('I have tested these momentum profile values on this rig')
        form_box.addWidget(self.profile_verified)
        actions = QHBoxLayout(); form_box.addLayout(actions)
        self.prepare_button = self.button('1  PREPARE', self.prepare, actions)
        self.run_button = self.button('2  RUN', self.run, actions)
        self.stop_button = self.button('STOP', self.stop, actions)
        self.stop_button.setStyleSheet('background:#a33843;color:white;font-weight:700')
        form_box.addWidget(QLabel('QP2 firmware required. No automatic movement on connection.\nSTOP sets motor drive to zero; the body may keep rotating.'))
        form_box.addStretch()
        right = QWidget(); rv = QVBoxLayout(right); split.addWidget(right)
        metrics = QGridLayout(); rv.addLayout(metrics)
        self.values = {}
        for i,(key,label) in enumerate([('MAG_HEADING','Heading °'),('SUN_ANGLE','Sun angle °'),
                                      ('BODY_RATE','Body rate °/s'),('POINTING_ERROR','Error °'),
                                      ('RW_CMD','Motor PWM %'),('EST_ANGLE','Estimated angle °')]):
            box = QGroupBox(label); b = QVBoxLayout(box); value = QLabel('—')
            value.setStyleSheet('font-size:23px;color:#5dd5fa'); b.addWidget(value)
            metrics.addWidget(box,i//3,i%3); self.values[key] = value
        self.elapsed = QLabel('No run recorded'); rv.addWidget(self.elapsed)
        self.fresh = QLabel('Waiting for telemetry'); rv.addWidget(self.fresh)
        self.plot = RatePlot(); rv.addWidget(self.plot)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(2000)
        rv.addWidget(self.log, 1)
        tools = QHBoxLayout(); rv.addLayout(tools)
        self.status_button = self.button('Status', lambda:self.radio.submit(self.radio.request('STATUS')), tools)
        self.capture_button = self.button('Capture photo', lambda:self.radio.submit(self.radio.request('CAPTURE')), tools)
        self.button('Export log / CSV', self.export, tools)
        rv.addWidget(QLabel('Capture sends a camera command; image download is not included.\nSettling is estimated from received telemetry, not an official competition score.'))
        for label in self.findChildren(QLabel):label.setWordWrap(True)
        split.setSizes([470,780])
        self.refresh()

    def spin(self, form, key, label, low, high, initial, integer=False):
        w = QDoubleSpinBox(); w.setRange(low,high); w.setDecimals(0 if integer else 2)
        w.setSingleStep(1 if integer else 0.1); w.setValue(initial)
        w.valueChanged.connect(self.invalidate); self.inputs[key] = w; form.addRow(label,w)

    def reference_changed(self, ref):
        self.inputs['target'].setRange(0 if ref=='MAG' else -90,359.99 if ref=='MAG' else 90)

    def settings(self):
        values = {}
        integer_fields = {'bias','cw_delta','cw_assist','cw_ms','ccw_delta','ccw_assist','ccw_ms','recovery_step','recovery_ms'}
        for key,w in self.inputs.items():
            value = w.currentText() if isinstance(w,QComboBox) else w.value()
            values[key] = int(value) if key in integer_fields else value
        return Settings(**values)

    def invalidate(self, *_):
        if self.phase.startswith('READY'):
            self.phase = 'SETTINGS CHANGED — prepare again'
            self.radio.ready = False
        if hasattr(self,'profile_verified'):
            self.profile_verified.setChecked(False)

    def scan(self):
        self.scan_button.setEnabled(False)
        self.status.setText('Scanning for SUNSEEK devices…')
        self.radio.submit(self.radio.scan())

    def on_devices(self, items):
        self.scan_button.setEnabled(True); self.devices.clear()
        for name,address in items:self.devices.addItem(f'{name}  [{address}]',address)
        self.status.setText(f'{len(items)} spacecraft found')

    def connect_device(self):
        if self.devices.currentData() and not self.connecting:
            self.connecting=True
            self.connect_button.setEnabled(False)
            self.radio.submit(self.radio.connect(self.devices.currentData()))

    def on_connected(self,value):
        self.is_connected=value
        self.connecting=False
        if not value:
            self.data.clear(); self.last_rate=0; self.last_error=0; self.last_valid=0
            self.hold_start=None; self.at_rest.setChecked(False)

    def on_error(self,text):
        self.phase='ERROR — not prepared'
        self.connecting=False
        self.run_start=None;self.hold_start=None
        self.status.setText(text); self.log.appendPlainText('ERROR '+text)
        self.scan_button.setEnabled(not self.is_connected)

    def on_state(self,text):
        self.phase=text; self.status.setText(text)
        if text=='RUNNING':
            self.run_start=time.monotonic(); self.hold_start=None; self.acquired=None
        if text.startswith(('STOPPED','DISCONNECTED','ERROR')):
            self.run_start=None; self.hold_start=None

    def prepare(self):
        try:
            s=self.settings(); s.plan()
            if s.strategy=='MOMENTUM' and not self.profile_verified.isChecked():
                raise ValueError('Verify the momentum profile values before using this strategy.')
            self.configuration=s
            self.logs.append('SETTINGS '+json.dumps(asdict(s)))
            self.phase='CHECKING';self.refresh()
            self.radio.submit(self.radio.execute(settings=s))
        except Exception as exc:self.on_error(str(exc))

    def run(self):
        self.phase='STARTING';self.at_rest.setChecked(False);self.refresh()
        self.radio.submit(self.radio.execute(run=True))

    def stop(self):
        self.phase='STOPPING';self.run_start=None;self.hold_start=None;self.refresh()
        self.radio.submit(self.radio.stop())

    def on_line(self,message):
        stamp=time.strftime('%H:%M:%S')
        entry=f'[{stamp}] {message}'
        self.logs.append(entry); self.logs=self.logs[-50000:]
        self.log.appendPlainText(entry)
        if not message.startswith('RX '): return
        line=message[3:]; fields=telemetry(line); self.data.update(fields)
        now=time.monotonic()
        for key,value in fields.items():
            if key in self.values:
                self.values[key].setText(value)
        if fields.get('GYRO')=='INVALID':self.last_rate=0
        if fields.get('EST_VALID')=='0':self.last_valid=0;self.hold_start=None
        if fields.get('EST_VALID')=='1':self.last_valid=now
        if 'BODY_RATE' in fields:
            try:
                rate=float(fields['BODY_RATE'])
                if math.isfinite(rate):self.plot.add(rate);self.last_rate=now
            except ValueError:pass
        if 'POINTING_ERROR' in fields:
            self.last_error=now
            try:
                error=float(fields['POINTING_ERROR']);rate=float(self.data.get('BODY_RATE','nan'))
                fresh=(now-self.last_rate<1 and now-self.last_valid<1)
                if self.run_start and self.configuration and fresh and math.isfinite(error) and math.isfinite(rate):
                    if abs(error)<=self.configuration.tolerance and abs(rate)<2:
                        if self.hold_start is None:self.hold_start=now
                        if self.acquired is None and now-self.hold_start>=self.configuration.hold:
                            self.acquired=now-self.run_start
                    else:self.hold_start=None
            except ValueError:self.hold_start=None
            self.records.append([stamp,round(now-self.run_start,3) if self.run_start else '',
                                 *[self.data.get(k,'') for k in ['TARGET','MAG_HEADING','SUN_ANGLE','EST_ANGLE','POINTING_ERROR','BODY_RATE','RW_CMD']]])
            self.records=self.records[-100000:]

    def refresh(self):
        if not hasattr(self,'prepare_button'): return
        busy=self.phase.startswith(('CHECKING','PREPARING','STARTING','RUNNING','STOPPING'))
        for w in self.inputs.values():w.setEnabled(not busy)
        self.prepare_button.setEnabled(self.is_connected and not busy and self.at_rest.isChecked())
        self.run_button.setEnabled(self.is_connected and self.phase.startswith('READY'))
        self.stop_button.setEnabled(self.is_connected)
        self.connect_button.setEnabled(not self.is_connected and not self.connecting)
        self.disconnect_button.setEnabled(self.is_connected)
        self.status_button.setEnabled(self.is_connected and not busy)
        self.capture_button.setEnabled(self.is_connected and not busy)
        age=time.monotonic()-self.last_rate
        self.fresh.setText('Live gyro telemetry' if self.is_connected and age<1 else 'Telemetry stale / unavailable — values may be old')
        if age>=1:self.hold_start=None
        if self.run_start:
            text=f'Elapsed: {time.monotonic()-self.run_start:.1f} s'
            if self.acquired is not None:text+=f'  |  First settled: {self.acquired:.2f} s (client estimate)'
            self.elapsed.setText(text)
        elif self.acquired is None:self.elapsed.setText('No active run')

    def save_settings(self):
        path,_=QFileDialog.getSaveFileName(self,'Save settings','','JSON (*.json)')
        if path:Path(path).write_text(json.dumps(asdict(self.settings()),indent=2))

    def load_settings(self):
        if self.phase.startswith(('CHECKING','PREPARING','STARTING','RUNNING','STOPPING')):return
        path,_=QFileDialog.getOpenFileName(self,'Load settings','','JSON (*.json)')
        if not path:return
        try:
            values=json.loads(Path(path).read_text());Settings(**values).plan()
            for key in ['reference','strategy']:
                self.inputs[key].setCurrentText(values.get(key,getattr(Settings(),key)))
            for key,w in self.inputs.items():
                if not isinstance(w,QComboBox):w.setValue(values.get(key,getattr(Settings(),key)))
            self.invalidate()
        except Exception as exc:self.on_error(str(exc))

    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export telemetry','','CSV (*.csv)')
        if not path:return
        try:
            with open(path,'w',newline='',encoding='utf-8') as f:
                writer=csv.writer(f);writer.writerow(['local_time','elapsed_s','target_deg','mag_heading_deg','sun_angle_deg','estimated_angle_deg','error_deg','body_rate_dps','motor_pwm_percent']);writer.writerows(self.records)
            Path(path).with_suffix('.log').write_text('\n'.join(self.logs),encoding='utf-8')
            self.log.appendPlainText('Saved CSV and command log.')
        except Exception as exc:self.on_error(str(exc))

    def closeEvent(self,event):
        if self.is_connected:
            QMessageBox.information(self,'Disconnect first','Press STOP, then Disconnect before closing. Disconnection alone does not stop the spacecraft.')
            event.ignore()
        else:event.accept()


STYLE='''
QWidget {background:#101d2c;color:#dce9f5;font-family:Segoe UI;font-size:12px;}
QGroupBox {border:1px solid #29465e;border-radius:6px;margin-top:13px;padding-top:12px;}
QGroupBox::title {subcontrol-origin:margin;left:10px;color:#65c8eb;}
QPushButton {background:#1d3a51;border:1px solid #365c77;border-radius:4px;padding:9px;}
QPushButton:hover {background:#28516d;} QPushButton:disabled {color:#627487;background:#172634;}
QComboBox,QDoubleSpinBox,QPlainTextEdit {background:#0b1623;border:1px solid #29465e;padding:5px;}
QCheckBox {padding:5px;} QSplitter::handle {background:#29465e;}
'''

if __name__=='__main__':
    app=QApplication(sys.argv)
    font_path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'
    if font_path.exists():QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont('Segoe UI',10));app.setStyleSheet(STYLE)
    window=Window();window.show()
    if '--smoke-test' in sys.argv:
        def smoke():
            for line in ['TM,MAG_HEADING,25.0,SUN_ANGLE,0.2','TM,BODY_RATE,0.1',
                         'TM,EST_VALID,1','TM,POINTING_ERROR,1.2,RW_CMD,0,EST_ANGLE,25.0']:
                window.on_line('RX '+line)
            if '--screenshot' in sys.argv:
                window.grab().save(sys.argv[sys.argv.index('--screenshot')+1])
            app.quit()
        QTimer.singleShot(500,smoke)
    sys.exit(app.exec())
