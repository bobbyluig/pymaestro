from maestro.bytecode.reader import BytecodeReader
from maestro.usc.protocol import uscSerialMode, ChannelMode, HomeMode


class UscSettings:
    def __init__(self):
        self.servosAvailable = 6
        self.servoPeriod = 156
        self.miniMaestroServoPeriod = 80000
        self.servoMultiplier = 1
        self.serialMode = uscSerialMode.SERIAL_MODE_UART_DETECT_BAUD_RATE
        self.fixedBaudRate = 9600
        self.enableCrc = False
        self.neverSuspend = False
        self.serialDeviceNumber = 12
        self.miniSscOffset = 0
        self.serialTimeout = 0
        self.scriptDone = True
        self.channelSettings = []
        self.enablePullups = True
        self.scriptInconsistent = False
        self.script = None
        self.bytecodeProgram = None

    def __len__(self):
        return len(self.channelSettings)

    def setAndCompileScript(self, script):
        self.script = None
        reader = BytecodeReader()
        self.bytecodeProgram = reader.read(script, len(self) != 6)
        self.script = script


class ChannelSetting:
    def __init__(self):
        self.name = ''
        self.mode = ChannelMode.Servo
        self.homeMode = HomeMode.Off
        self.home = 6000
        self.minimum = 3968
        self.maximum = 8000
        self.neutral = 6000
        self.range = 1905
        self.speed = 0
        self.acceleration = 0
