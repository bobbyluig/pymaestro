import time

import usb

from maestro.usc.protocol import *
from maestro.usc.settings import UscSettings, ChannelSetting


class Range:
    def __init__(self, numBytes, minimumValue, maximumValue):
        self.bytes = numBytes
        self.minimumValue = minimumValue
        self.maximumValue = maximumValue

    def signed(self):
        return self.minimumValue < 0

    @staticmethod
    def u16():
        return Range(2, 0, 0xFFFF)

    @staticmethod
    def u12():
        return Range(2, 0, 0x0FFF)

    @staticmethod
    def u10():
        return Range(2, 0, 0x03FF)

    @staticmethod
    def u8():
        return Range(1, 0, 0xFF)

    @staticmethod
    def u7():
        return Range(1, 0, 0x7F)

    @staticmethod
    def boolean():
        return Range(1, 0, 1)


class Usc:
    # Pololu's USB vendor id.
    vendorID = 0x1ffb

    # The Micro/Mini Maestro's product ID.
    productIDArray = [0x0089, 0x008a, 0x008b, 0x008c]

    # Instructions are executed at 12 MHZ.
    INSTRUCTION_FREQUENCY = 12000000

    # The number of parameter bytes per servo.
    servoParameterBytes = 9

    # Stack and call sizes.
    MicroMaestroStackSize = 32
    MicroMaestroCallStackSize = 10
    MiniMaestroStackSize = 126
    MiniMaestroCallStackSize = 126

    def __init__(self, device):
        """
        Create a Usc object. Raises ConnectionError if device is invalid.
        :param device: A Maestro device found by pyusb. Must be of class 'usb.core.Device'.
        """

        if type(device) != usb.core.Device:
            raise ConnectionError('Unable to connect to the Maestro.')

        self.dev = device

        self.productID = self.dev.idProduct

        if self.productID == self.productIDArray[0]:
            self.servoCount = 6
        elif self.productID == self.productIDArray[1]:
            self.servoCount = 12
        elif self.productID == self.productIDArray[2]:
            self.servoCount = 18
        elif self.productID == self.productIDArray[3]:
            self.servoCount = 24
        else:
            raise Exception('Unknown product ID {:02x}.'.format(self.productID))

        self.serialNumber = self.dev.serial_number
        self.microMaestro = self.servoCount == 6
        self.subroutineOffsetBlocks = 512 if not self.microMaestro else 64
        self.maxScriptLength = 8192 if not self.microMaestro else 1024
        self.firmwareVersionString = self.getFirmwareVersion()

        self._privateFirmwareVersionMajor = 0xFF
        self._privateFirmwareVersionMinor = 0xFF

    def close(self):
        self.dev.close()

    def getProductID(self):
        return self.productID

    def specifyServo(self, p, servo):
        """
        Returns the parameter number for the parameter of a given servo,
        given the corresponding parameter number for servo 0.
        :param p: e.g. PARAMETER_SERVO0_HOME
        :param servo: Channel number.
        """

        return p + servo * self.servoParameterBytes

    def _microMaestro(self):
        return self.servoCount == 6

    @staticmethod
    def _exponentialSpeedToNormalSpeed(exponentialSpeed):
        mantissa = exponentialSpeed >> 3
        exponent = exponentialSpeed & 7
        return mantissa * (1 << exponent)

    @staticmethod
    def _normalSpeedToExponentialSpeed(normalSpeed):
        mantissa = normalSpeed
        exponent = 0

        while True:
            if mantissa < 32:
                return exponent + (mantissa << 3)

            if exponent == 7:
                return 0xFF

            exponent += 1
            mantissa >>= 1

    @staticmethod
    def positionToMicroseconds(position):
        return position / 4

    @staticmethod
    def microsecondsToPosition(us):
        return us * 4

    @staticmethod
    def periodToMicroseconds(period, servos_available):
        return period * 256 * servos_available / 12

    @staticmethod
    def microsecondsToPeriod(us, servos_avaiable):
        return int(round(us / 256 * 12 / servos_avaiable))

    @staticmethod
    def _convertSpbrgToBps(spbrg):
        if spbrg == 0:
            return 0
        else:
            return int((Usc.INSTRUCTION_FREQUENCY + (spbrg + 1) / 2) / (spbrg + 1))

    @staticmethod
    def _convertBpsToSpbrg(bps):
        if bps == 0:
            return 0
        else:
            return int((Usc.INSTRUCTION_FREQUENCY - bps / 2) / bps)

    @staticmethod
    def _channelToPort(channel):
        if channel <= 3:
            return channel
        elif channel < 6:
            return channel + 2
        else:
            raise Exception('Invalid channel number {}.'.format(channel))

    def microMaestro(self):
        return self.servoCount == 6

    def stackSize(self):
        if self.microMaestro:
            return self.MicroMaestroStackSize
        else:
            return self.MiniMaestroStackSize

    def callStackSize(self):
        if self.microMaestro:
            return self.MicroMaestroCallStackSize
        else:
            return self.MiniMaestroCallStackSize

    @staticmethod
    def getConnectedDevices():
        return list(usb.core.find(find_all=True, idVendor=Usc.vendorID))

    def firmwareVersionMajor(self):
        if self._privateFirmwareVersionMajor == 0xFF:
            self.getFirmwareVersion()

        return self._privateFirmwareVersionMajor

    def firmwareVersionMinor(self):
        if self._privateFirmwareVersionMinor == 0xFF:
            self.getFirmwareVersion()

        return self._privateFirmwareVersionMinor

    def firmwareVersionString(self):
        return '{:d}.{:02d}'.format(self._privateFirmwareVersionMajor, self._privateFirmwareVersionMinor)

    def getFirmwareVersion(self):
        buffer = self.dev.ctrl_transfer(0x80, 6, 0x0100, 0x0000, 0x0012)
        self._privateFirmwareVersionMinor = (buffer[12] & 0xF) + (buffer[12] >> 4 & 0xF) * 10
        self._privateFirmwareVersionMajor = (buffer[13] & 0xF) + (buffer[13] >> 4 & 0xF) * 10

    def eraseScript(self):
        """
        Erases the entire script and subroutine address table from the devices.
        """

        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_ERASE_SCRIPT, 0, 0)

    def restartScriptAtSubroutine(self, subroutine):
        """
        Stops and resets the script, sets the program counter to the beginning of the
        specified subroutine.  After this function has run, the script will be paused,
        so you must use setScriptDone() to start it.
        """

        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_RESTART_SCRIPT_AT_SUBROUTINE, 0, 0, subroutine)

    def restartScriptAtSubroutineWithParameter(self, subroutine, parameter):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_ERASE_SCRIPT_WITH_PARAMETER, parameter, subroutine)

    def restartScript(self):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_RESTART_SCRIPT, 0, 0)

    def writeScript(self, bytecode):
        for block in range((len(bytecode) + 15) // 16):
            block_bytes = bytearray((0x00,) * 16)

            for j in range(16):
                if block * 16 + j < len(bytecode):
                    block_bytes[j] = bytecode[block * 16 + j]
                else:
                    block_bytes[j] = 0xFF

            self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_WRITE_SCRIPT, 0, block, block_bytes)

    def setSubroutines(self, subroutineAddresses, subroutineCommands):
        subroutineData = bytearray((0xFF,) * 256)

        for name, value in subroutineAddresses.items():
            bytecode = subroutineCommands[name]

            if bytecode == Opcode.CALL:
                continue

            subroutineData[2 * (bytecode - 128)] = value % 256
            subroutineData[2 * (bytecode - 128) + 1] = value >> 8

        for block in range(16):
            block_bytes = bytearray((0x00,) * 16)

            for j in range(16):
                block_bytes[j] = subroutineData[block * 16 + j]

            self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_WRITE_SCRIPT, 0, block + self.subroutineOffsetBlocks,
                                   block_bytes)

    def setScriptDone(self, value):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_SET_SCRIPT_DONE, value, 0)

    def startBootloader(self):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_START_BOOTLOADER, 0, 0)

    def reinitalize(self):
        self._reinitialize(50)

    def _reinitialize(self, waitTime):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_REINITIALIZE, 0, 0)

        if not self.microMaestro:
            self.getVariables('variables')

        time.sleep(waitTime / 1000)

    def clearErrors(self):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_CLEAR_ERRORS, 0, 0)

    def getVariables(self, out):
        """
        Gets a set of status information for the Maestro.
        :param out: The type of status.
            variables:  Gets a MaestroVariables struct representing the current status of the device.
            servos:     Gets an array of ServoStatus structs representing the current status of all the channels.
            stack:      Gets an array of shorts[] representing the current stack.
                        The maximum size of the array is stackSize.
            callStack:  Gets an array of ushorts[] representing the current stack.
                        The maximum size of the array is callStackSize.
        """

        if self.microMaestro:
            variables, servos = self._getVariableMicroMaestro()

            if out == 'variables':
                return variables
            elif out == 'servos':
                return servos
            elif out == 'stack':
                return variables.stack
            elif out == 'callStack':
                return variables.callStack
            else:
                raise Exception('Unknown type of desired output %s.' % out)

        else:
            return self._getVariableMiniMaestro(out)

    def _getVariableMicroMaestro(self):
        packed = self.dev.ctrl_transfer(0xC0, uscRequest.REQUEST_GET_VARIABLES, 0, 0,
                                        MicroMaestroVariables.struct.size + self.servoCount * ServoStatus.struct.size)

        var_packed = packed[0:MicroMaestroVariables.struct.size]
        servo_packed = packed[MicroMaestroVariables.struct.size:]

        variables = MicroMaestroVariables(var_packed)

        servos = []
        for i in range(self.servoCount):
            servos.append(ServoStatus(servo_packed[i * ServoStatus.struct.size:(i + 1) * ServoStatus.struct.size]))

        return variables, servos

    def _getVariableMiniMaestro(self, out):
        if out == 'variables':
            packed = self.dev.ctrl_transfer(0xC0, uscRequest.REQUEST_GET_VARIABLES, 0, 0,
                                            MiniMaestroVariables.struct.size)

            if len(packed) != MiniMaestroVariables.struct.size:
                raise Exception('Short read: {} < {}.'.format(len(packed), MiniMaestroVariables.struct.size))

            return MiniMaestroVariables(packed)

        elif out == 'servos':
            packed = self.dev.ctrl_transfer(0xC0, uscRequest.REQUEST_GET_SERVO_SETTINGS, 0, 0,
                                            self.servoCount * ServoStatus.struct.size)

            if len(packed) != ServoStatus.struct.size * self.servoCount:
                raise Exception('Short read: {} < {}.'.format(len(packed), ServoStatus.struct.size))

            servos = []
            for i in range(self.servoCount):
                servos.append(ServoStatus(packed[i * ServoStatus.struct.size:(i + 1) * ServoStatus.struct.size]))

            return servos

        elif out == 'stack':
            packed = self.dev.ctrl_transfer(0xC0, uscRequest.REQUEST_GET_STACK, 0, 0, 2 * self.MiniMaestroStackSize)
            return packed.tolist()

        elif out == 'callStack':
            packed = self.dev.ctrl_transfer(0xC0, uscRequest.REQUEST_GET_CALL_STACK, 0, 0,
                                            2 * self.MiniMaestroCallStackSize)
            return packed.tolist()

        else:
            raise Exception('Unknown type of desired output {}.'.format(out))

    def setTarget(self, servo, value):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_SET_TARGET, value, servo)

    def setSpeed(self, servo, value):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_SET_SERVO_VARIABLE, value, servo)

    def setAcceleration(self, servo, value):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_SET_SERVO_VARIABLE, value, servo | 0x80)

    def setUscSettings(self, settings, newScript):
        self._setRawParameter(uscParameter.PARAMETER_SERIAL_MODE, settings.serialMode)
        self._setRawParameter(uscParameter.PARAMETER_SERIAL_FIXED_BAUD_RATE,
                              self._convertBpsToSpbrg(settings.fixedBaudRate))
        self._setRawParameter(uscParameter.PARAMETER_SERIAL_ENABLE_CRC, int(settings.enableCrc))
        self._setRawParameter(uscParameter.PARAMETER_SERIAL_NEVER_SUSPEND, int(settings.neverSuspend))
        self._setRawParameter(uscParameter.PARAMETER_SERIAL_DEVICE_NUMBER, settings.serialDeviceNumber)
        self._setRawParameter(uscParameter.PARAMETER_SERIAL_MINI_SSC_OFFSET, settings.miniSscOffset)
        self._setRawParameter(uscParameter.PARAMETER_SERIAL_TIMEOUT, settings.serialTimeout)
        self._setRawParameter(uscParameter.PARAMETER_SCRIPT_DONE, int(settings.scriptDone))

        if self.microMaestro:
            self._setRawParameter(uscParameter.PARAMETER_SERVOS_AVAILABLE, settings.servosAvailable)
            self._setRawParameter(uscParameter.PARAMETER_SERVO_PERIOD, settings.servoPeriod)
        else:
            self._setRawParameter(
                uscParameter.PARAMETER_MINI_MAESTRO_SERVO_PERIOD_L, settings.miniMaestroServoPeriod & 0xFF)
            self._setRawParameter(
                uscParameter.PARAMETER_MINI_MAESTRO_SERVO_PERIOD_HU, settings.miniMaestroServoPeriod >> 8)

            if settings.servoMultiplier < 1:
                multiplier = 0
            elif settings.servoMultiplier > 256:
                multiplier = 255
            else:
                multiplier = settings.servoMultiplier - 1

            self._setRawParameter(uscParameter.PARAMETER_SERVO_MULTIPLIER, multiplier)

        if self.servoCount > 18:
            self._setRawParameter(uscParameter.PARAMETER_ENABLE_PULLUPS, int(settings.enablePullups))

        ioMask = 0
        outputMask = 0
        channelModeBytes = bytearray((0,) * 6)

        for i in range(self.servoCount):
            setting = settings.channelSettings[i]

            if self.microMaestro:
                if setting.mode == ChannelMode.Input or setting.mode == ChannelMode.Output:
                    ioMask |= 1 << self._channelToPort(i)

                if setting.mode == ChannelMode.Output:
                    outputMask |= 1 << self._channelToPort(i)
            else:
                channelModeBytes[i >> 2] |= setting.mode << ((i & 3) << 1)

            correctedHomeMode = setting.homeMode

            if setting.mode == ChannelMode.Input:
                correctedHomeMode = HomeMode.Ignore

            if correctedHomeMode == HomeMode.Off:
                home = 0
            elif correctedHomeMode == HomeMode.Ignore:
                home = 1
            else:
                home = setting.home

            self._setRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_HOME, i), home)
            self._setRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_MIN, i), int(setting.minimum / 64))
            self._setRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_MAX, i), int(setting.maximum / 64))
            self._setRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_NEUTRAL, i), setting.neutral)
            self._setRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_RANGE, i), int(setting.range / 127))
            self._setRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_SPEED, i),
                                  self._normalSpeedToExponentialSpeed(setting.speed))
            self._setRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_ACCELERATION, i),
                                  setting.acceleration)

        if self.microMaestro:
            self._setRawParameter(uscParameter.PARAMETER_IO_MASK_C, ioMask)
            self._setRawParameter(uscParameter.PARAMETER_OUTPUT_MASK_C, outputMask)
        else:
            for i in range(6):
                self._setRawParameter(uscParameter.PARAMETER_CHANNEL_MODES_0_3 + i, channelModeBytes[i])

        if newScript:
            self.loadProgram(settings.bytecodeProgram, CRC=True)

    def _setRawParameter(self, parameter, value):
        parameterRange = Usc.getRange(parameter)
        Usc.requireArgumentRange(value, parameterRange.minimumValue, parameterRange.maximumValue, parameter)
        self._setRawParameterNoChecks(parameter, value, parameterRange.bytes)

    def _setRawParameterNoChecks(self, parameter, value, numBytes):
        index = (numBytes << 8) + parameter
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_SET_PARAMETER, value, index)

    def _getRawParameter(self, parameter):
        parameterRange = Usc.getRange(parameter)
        array = self.dev.ctrl_transfer(0xC0, uscRequest.REQUEST_GET_PARAMETER, 0, parameter, parameterRange.bytes)

        if parameterRange.bytes == 1:
            return int(struct.unpack('<B', array)[0])
        else:
            return int(struct.unpack('<H', array)[0])

    def getUscSettings(self):
        settings = UscSettings()

        settings.serialMode = self._getRawParameter(uscParameter.PARAMETER_SERIAL_MODE)
        settings.fixedBaudRate = self._convertSpbrgToBps(
            self._getRawParameter(uscParameter.PARAMETER_SERIAL_FIXED_BAUD_RATE))
        settings.enableCrc = self._getRawParameter(uscParameter.PARAMETER_SERIAL_ENABLE_CRC) != 0
        settings.neverSuspend = self._getRawParameter(uscParameter.PARAMETER_SERIAL_NEVER_SUSPEND) != 0
        settings.serialDeviceNumber = self._getRawParameter(uscParameter.PARAMETER_SERIAL_DEVICE_NUMBER)
        settings.miniSscOffset = self._getRawParameter(uscParameter.PARAMETER_SERIAL_MINI_SSC_OFFSET)
        settings.serialTimeout = self._getRawParameter(uscParameter.PARAMETER_SERIAL_TIMEOUT)
        settings.scriptDone = self._getRawParameter(uscParameter.PARAMETER_SCRIPT_DONE) != 0

        if self.microMaestro:
            settings.servosAvailable = self._getRawParameter(uscParameter.PARAMETER_SERVOS_AVAILABLE)
            settings.servoPeriod = self._getRawParameter(uscParameter.PARAMETER_SERVO_PERIOD)
        else:
            tmp = self._getRawParameter(uscParameter.PARAMETER_MINI_MAESTRO_SERVO_PERIOD_HU) << 8
            tmp |= self._getRawParameter(uscParameter.PARAMETER_MINI_MAESTRO_SERVO_PERIOD_L)
            settings.miniMaestroServoPeriod = tmp

            settings.servoMultiplier = self._getRawParameter(uscParameter.PARAMETER_SERVO_MULTIPLIER) + 1

        if self.servoCount > 18:
            settings.enablePullups = self._getRawParameter(uscParameter.PARAMETER_ENABLE_PULLUPS) != 0

        ioMask = 0
        outputMask = 0
        channelModeBytes = []

        if self.microMaestro:
            ioMask = self._getRawParameter(uscParameter.PARAMETER_IO_MASK_C)
            outputMask = self._getRawParameter(uscParameter.PARAMETER_OUTPUT_MASK_C)
        else:
            for i in range(6):
                channelModeBytes.append(self._getRawParameter(uscParameter.PARAMETER_CHANNEL_MODES_0_3 + i))

        for i in range(self.servoCount):
            setting = ChannelSetting()

            if self.microMaestro:
                bitmask = 1 << Usc._channelToPort(i)
                if (ioMask & bitmask) == 0:
                    setting.mode = ChannelMode.Servo
                elif (outputMask & bitmask) == 0:
                    setting.mode = ChannelMode.Input
                else:
                    setting.mode = ChannelMode.Output
            else:
                setting.mode = (channelModeBytes[i >> 2] >> ((i & 3) << 1)) & 3

            home = self._getRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_HOME, i))

            if home == 0:
                setting.homeMode = HomeMode.Off
                setting.home = 0
            elif home == 1:
                setting.homeMode = HomeMode.Ignore
                setting.home = 0
            else:
                setting.homeMode = HomeMode.Goto
                setting.home = home

            setting.minimum = 64 * self._getRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_MIN, i))
            setting.maximum = 64 * self._getRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_MAX, i))
            setting.neutral = self._getRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_NEUTRAL, i))
            setting.range = 127 * self._getRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_RANGE, i))
            setting.speed = self._exponentialSpeedToNormalSpeed(
                self._getRawParameter(self.specifyServo(uscParameter.PARAMETER_SERVO0_SPEED, i)))
            setting.acceleration = self._getRawParameter(
                self.specifyServo(uscParameter.PARAMETER_SERVO0_ACCELERATION, i))

            settings.channelSettings.append(setting)

        return settings

    @staticmethod
    def requireArgumentRange(argumentValue, minimum, maximum, argumentName):
        if argumentValue < minimum or argumentValue > maximum:
            raise Exception('The %s must be between {} and {} but the value given was {}.'
                            .format(argumentName, minimum, maximum, argumentValue))

    def restoreDefaultConfiguration(self):
        self._setRawParameterNoChecks(uscParameter.PARAMETER_INITIALIZED, 0xFF, 1)
        self._reinitialize(1500)

    def fixSettings(self, settings):
        warnings = []

        if len(settings) > self.servoCount:
            warnings.append('The settings loaded include settings for {} channels, '
                            'but this device has only {} channels. The extra channel settings will be ignored.'
                            .format(len(settings), self.servoCount))
            del settings.channelSettings[self.servoCount:]

        if len(settings) < self.servoCount:
            warnings.append('The settings loaded include settings for only {} channels, '
                            'but this device has {} channels. '
                            'The other channels will be initialized with default settings.'
                            .format(len(settings), self.servoCount))
            while len(settings) < self.servoCount:
                cs = ChannelSetting()
                if self.microMaestro and settings.servosAvailable <= len(settings):
                    cs.mode = ChannelMode.Input
                settings.channelSettings.append(cs)

        for cs in settings.channelSettings:
            if cs.mode == ChannelMode.Input:
                cs.homeMode = HomeMode.Ignore
                cs.minimum = 0
                cs.maximum = 1024
                cs.speed = 0
                cs.acceleration = 0
                cs.neutral = 1024
                cs.range = 1905
            elif cs.mode == ChannelMode.Output:
                cs.minimum = 3986
                cs.maximum = 8000
                cs.speed = 0
                cs.acceleration = 0
                cs.neutral = 6000
                cs.range = 1905

        if settings.serialDeviceNumber >= 128:
            settings.serialDeviceNumber = 12
            warnings.append('The serial device number must be less than 128. It will be changed to 12.')

        return warnings

    @staticmethod
    def getRange(parameterId):
        if parameterId in [uscParameter.PARAMETER_INITIALIZED,
                           uscParameter.PARAMETER_SERVOS_AVAILABLE,
                           uscParameter.PARAMETER_SERVO_PERIOD,
                           uscParameter.PARAMETER_MINI_MAESTRO_SERVO_PERIOD_L,
                           uscParameter.PARAMETER_SERVO_MULTIPLIER,
                           uscParameter.PARAMETER_CHANNEL_MODES_0_3,
                           uscParameter.PARAMETER_CHANNEL_MODES_4_7,
                           uscParameter.PARAMETER_CHANNEL_MODES_8_11,
                           uscParameter.PARAMETER_CHANNEL_MODES_12_15,
                           uscParameter.PARAMETER_CHANNEL_MODES_16_19,
                           uscParameter.PARAMETER_CHANNEL_MODES_20_23,
                           uscParameter.PARAMETER_ENABLE_PULLUPS]:
            return Range.u8()
        elif parameterId in [uscParameter.PARAMETER_MINI_MAESTRO_SERVO_PERIOD_HU,
                             uscParameter.PARAMETER_SERIAL_TIMEOUT,
                             uscParameter.PARAMETER_SERIAL_FIXED_BAUD_RATE,
                             uscParameter.PARAMETER_SCRIPT_CRC]:
            return Range.u16()
        elif parameterId in [uscParameter.PARAMETER_SERIAL_NEVER_SUSPEND,
                             uscParameter.PARAMETER_SERIAL_ENABLE_CRC,
                             uscParameter.PARAMETER_SCRIPT_DONE]:
            return Range.boolean()
        elif parameterId == uscParameter.PARAMETER_SERIAL_DEVICE_NUMBER:
            return Range.u7()
        elif parameterId == uscParameter.PARAMETER_SERIAL_MODE:
            return Range(1, 0, 3)
        elif parameterId == uscParameter.PARAMETER_SERIAL_BAUD_DETECT_TYPE:
            return Range(1, 0, 1)
        elif parameterId == uscParameter.PARAMETER_SERIAL_MINI_SSC_OFFSET:
            return Range(1, 0, 254)
        else:
            servoParameter = ((int(parameterId) - int(uscParameter.PARAMETER_SERVO0_HOME)) % 9) \
                             + int(uscParameter.PARAMETER_SERVO0_HOME)
            if servoParameter in [int(uscParameter.PARAMETER_SERVO0_SPEED),
                                  int(uscParameter.PARAMETER_SERVO0_MAX),
                                  int(uscParameter.PARAMETER_SERVO0_MIN),
                                  int(uscParameter.PARAMETER_SERVO0_ACCELERATION)]:
                return Range.u8()
            elif servoParameter in [int(uscParameter.PARAMETER_SERVO0_HOME),
                                    int(uscParameter.PARAMETER_SERVO0_NEUTRAL)]:
                return Range(2, 0, 32440)
            elif servoParameter == int(uscParameter.PARAMETER_SERVO0_RANGE):
                return Range(1, 1, 50)
            else:
                raise Exception('Invalid parameterId {}, can not determine the range of this parameter.'
                                .format(int(parameterId)))

    def setPWM(self, dutyCycle, period):
        self.dev.ctrl_transfer(0x40, uscRequest.REQUEST_SET_PWM, dutyCycle, period)

    def disablePWM(self):
        if self.getProductID() == 0x008a:
            self.setTarget(8, 0)
        else:
            self.setTarget(12, 0)

    def loadProgram(self, program, CRC=False):
        self.setScriptDone(1)
        byteList = program.getByteList()

        if len(byteList) > self.maxScriptLength:
            raise Exception('Script is too long for device ({} bytes).'.format(byteList))

        if len(byteList) < self.maxScriptLength:
            byteList.append(Opcode.QUIT)

        self.eraseScript()
        self.setSubroutines(program.subroutineAddresses, program.subroutineCommands)
        self.writeScript(byteList)

        if CRC:
            self._setRawParameter(uscParameter.PARAMETER_SCRIPT_CRC, program.getCRC())

        self._reinitialize(100)
