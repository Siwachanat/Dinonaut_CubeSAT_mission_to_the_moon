"""Pure SunSeek command planning and telemetry framing."""
import math
from dataclasses import dataclass

SERVICE = '6e400001-b5a3-f393-e0a9-e50e24dcca9e'
RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'
TX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e'


class Lines:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        out = []
        while b'\n' in self.buffer:
            line, _, rest = self.buffer.partition(b'\n')
            self.buffer = bytearray(rest)
            out.append(line.decode('utf-8', errors='replace').strip())
        if len(self.buffer) > 8192:
            self.buffer.clear()
            raise ValueError('Telemetry frame exceeded 8192 bytes')
        return [line for line in out if line]


def checked(value, low, high, name, integer=False):
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name}: expected {low} to {high}')
    if integer and value != int(value):
        raise ValueError(f'{name}: must be an integer')
    return int(value) if integer else value


@dataclass(frozen=True)
class Settings:
    reference: str = 'MAG'
    strategy: str = 'REACTION'
    target: float = 0
    tolerance: float = 3
    hold: float = 2
    kp: float = 0.5
    kd: float = 1
    bias: int = 40
    cw_delta: int = 10
    cw_assist: int = 40
    cw_ms: int = 100
    ccw_delta: int = -10
    ccw_assist: int = 20
    ccw_ms: int = 100
    recovery_step: int = 1
    recovery_ms: int = 100
    trigger: float = 5

    def plan(self):
        if self.reference not in ('MAG', 'SUN') or self.strategy not in ('REACTION', 'MOMENTUM'):
            raise ValueError('Invalid reference or strategy')
        checked(self.target, 0 if self.reference == 'MAG' else -90,
                359.99 if self.reference == 'MAG' else 90, 'Target')
        checked(self.tolerance, 0.01, 30, 'Tolerance')
        checked(self.hold, 0, 60, 'Hold')
        checked(self.kp, 0, 20, 'Kp'); checked(self.kd, 0, 20, 'Kd')
        checked(self.bias, 0, 100, 'Bias', True)
        commands = ['MISSION_RESET', 'ADCS_MODE,MANUAL',
                    f'ADCS_STRATEGY,{self.strategy}', f'ADCS_REFERENCE,{self.reference}',
                    f'SET_TARGET,{self.target:g}', f'ADCS_TUNE,{self.kp:g},{self.kd:g},{self.bias}']
        if self.strategy == 'MOMENTUM':
            checked(self.cw_delta, 1, 100, 'CW delta', True)
            checked(self.ccw_delta, -100, -1, 'CCW delta', True)
            checked(self.bias + self.cw_delta, 0, 100, 'CW target')
            checked(self.bias + self.ccw_delta, 0, 100, 'CCW target')
            for name in ('cw', 'ccw'):
                checked(getattr(self, name + '_assist'), -100, 100, name + ' assist', True)
                checked(getattr(self, name + '_ms'), 0, 10000, name + ' duration', True)
            checked(self.recovery_step, 1, 100, 'Recovery step', True)
            checked(self.recovery_ms, 10, 10000, 'Recovery interval', True)
            checked(self.trigger, 0.1, 100, 'Trigger')
            commands += [f'MOM_PROFILE_BIAS,{self.bias}',
                         f'MOM_PROFILE_CW,{self.cw_delta},{self.cw_assist},{self.cw_ms}',
                         f'MOM_PROFILE_CCW,{self.ccw_delta},{self.ccw_assist},{self.ccw_ms}',
                         f'MOM_PROFILE_RECOVERY,{self.recovery_step},{self.recovery_ms}',
                         f'MOM_PROFILE_TRIGGER,{self.trigger:g}']
        return commands + ['ADCS_PREPARE', 'MISSION_CLEAR',
                           f'MISSION_TARGET,{self.target:g},{self.tolerance:g},{self.hold:g}',
                           'MISSION_PREPARE']


def check_preflight(line):
    fields = line.split(',')
    if len(fields) != 6 or fields[:3] != ['ACK', 'QP_STATUS', '2']:
        raise ValueError('Upload the included QP2 firmware before PREPARE.')
    if fields[3] != 'MANUAL' or fields[4] != 'STOPPED':
        raise ValueError('Press STOP and wait for physical rest before PREPARE.')
    if fields[5] not in ('IDLE', 'READY', 'ABORTED', 'COMPLETE', 'FAILED', 'TIME_LIMIT_REACHED'):
        raise ValueError('Mission active. Press STOP first.')


def telemetry(line):
    fields = line.split(',')
    if not fields or fields[0] != 'TM':
        return {}
    return dict(zip(fields[1::2], fields[2::2]))


def acknowledgement(command, line):
    key = command.split(',')[0]
    return line == 'ACK,' + key or line.startswith('ACK,' + key + ',') or (key == 'PING' and line == 'PONG')
