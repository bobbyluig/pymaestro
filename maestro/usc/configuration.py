import xml.etree.ElementTree as ET

from maestro.usc.protocol import uscSerialMode, ChannelMode, HomeMode
from maestro.usc.settings import UscSettings, ChannelSetting


class ConfigurationFile:
    @staticmethod
    def load(file):
        warnings = []

        tree = ET.parse(file)
        root = tree.getroot()

        settings = UscSettings()

        def getKey(key, warn=True):
            key = root.find(key)

            if key is None and warn:
                warnings.append('The {} setting was missing.'.format(key))

            return key

        def getAttrib(dict, key):
            if key in dict:
                return True
            else:
                warnings.append('The {} attribute was missing'.format(key))
                return False

        def parseBool(value):
            value = value.lower()

            if value == 'false':
                return False
            elif value == 'true':
                return True
            else:
                return None

        def parseInt(value, type):
            try:
                value = int(value)
            except ValueError:
                return None

            if type == 'u8' and 0 <= value <= 255:
                return value
            elif type == 'u16' and 0 <= value <= 65535:
                return value
            elif type == 'u32' and 0 <= value <= 4294967295:
                return value

            return None

        assert (root.tag == 'UscSettings')

        if not 'version' in root.attrib:
            warnings.append('This file has no version number, so it might have been read incorrectly.')
        elif root.attrib['version'] != '1':
            warnings.append('Unrecognized settings file version {}.'.format(root.attrib['version']))

        NeverSuspend = getKey('NeverSuspend')
        SerialMode = getKey('SerialMode')
        FixedBaudRate = getKey('FixedBaudRate')
        SerialTimeout = getKey('SerialTimeout')
        EnableCrc = getKey('EnableCrc')
        SerialDeviceNumber = getKey('SerialDeviceNumber')
        SerialMiniSscOffset = getKey('SerialMiniSscOffset')

        Script = getKey('Script')
        Channels = getKey('Channels')

        ServosAvailable = getKey('ScriptAvailable', warn=False)
        ServoPeriod = getKey('ServoPeriod', warn=False)
        EnablePullups = getKey('EnablePullups', warn=False)
        MiniMaestroServoPeriod = getKey('MiniMaestroServoPeriod', warn=False)
        ServoMultiplier = getKey('ServoMultiplier', warn=False)

        if Channels is not None:
            for channel in Channels:
                cs = ChannelSetting()
                attrib = channel.attrib

                if getAttrib(attrib, 'name'):
                    cs.name = attrib['name']

                if getAttrib(attrib, 'mode'):
                    mode = attrib['mode'].lower()

                    if mode == 'servomultiplied':
                        cs.mode = ChannelMode.ServoMultiplied
                    elif mode == 'servo':
                        cs.mode = ChannelMode.Servo
                    elif mode == 'input':
                        cs.mode = ChannelMode.Input
                    elif mode == 'output':
                        cs.mode = ChannelMode.Output
                    else:
                        warnings.append('Invalid mode {}.'.format(mode))

                if getAttrib(attrib, 'homemode'):
                    mode = attrib['homemode'].lower()

                    if mode == 'goto':
                        cs.homeMode = HomeMode.Goto
                    elif mode == 'off':
                        cs.homeMode = HomeMode.Off
                    elif mode == 'ignore':
                        cs.homeMode = HomeMode.Ignore

                if getAttrib(attrib, 'min'):
                    value = parseInt(attrib['min'], 'u16')

                    if value is not None:
                        cs.minimum = value
                    else:
                        warnings.append('Error in value of min. Skipping.')

                if getAttrib(attrib, 'max'):
                    value = parseInt(attrib['max'], 'u16')

                    if value is not None:
                        cs.maximum = value
                    else:
                        warnings.append('Error in value of max. Skipping.')

                if getAttrib(attrib, 'home'):
                    value = parseInt(attrib['home'], 'u16')

                    if value is not None:
                        cs.home = value
                    else:
                        warnings.append('Error in value of home. Skipping.')

                if getAttrib(attrib, 'speed'):
                    value = parseInt(attrib['speed'], 'u16')

                    if value is not None:
                        cs.speed = value
                    else:
                        warnings.append('Error in value of speed. Skipping.')

                if getAttrib(attrib, 'acceleration'):
                    value = parseInt(attrib['acceleration'], 'u8')

                    if value is not None:
                        cs.acceleration = value
                    else:
                        warnings.append('Error in value of acceleration. Skipping.')

                if getAttrib(attrib, 'neutral'):
                    value = parseInt(attrib['neutral'], 'u16')

                    if value is not None:
                        cs.neutral = value
                    else:
                        warnings.append('Error in value of neutral. Skipping.')

                if getAttrib(attrib, 'range'):
                    value = parseInt(attrib['range'], 'u16')

                    if value is not None:
                        cs.range = value
                    else:
                        warnings.append('Error in value of range. Skipping.')

                settings.channelSettings.append(cs)

        if Script is not None:
            if getAttrib(Script.attrib, 'ScriptDone'):
                value = parseBool(Script.attrib['ScriptDone'])

                if value is not None:
                    settings.scriptDone = value
                else:
                    warnings.append('Error in value of ScriptDone. Skipping.')

            script = Script.text

            try:
                settings.setAndCompileScript(script)
            except Exception as e:
                warnings.append('Error compiling script from XML file: {}'.format(e))
                settings.scriptInconsistent = True

        if NeverSuspend is not None:
            value = parseBool(NeverSuspend.text)

            if value is not None:
                settings.fixedBaudRate = value
            else:
                warnings.append('Error in value of NeverSuspend. Skipping.')

        if SerialMode is not None:
            value = SerialMode.text

            if value == 'UART_FIXED_BAUD_RATE':
                settings.serialMode = uscSerialMode.SERIAL_MODE_UART_FIXED_BAUD_RATE
            elif value == 'USB_DUAL_PORT':
                settings.serialMode = uscSerialMode.SERIAL_MODE_USB_DUAL_PORT
            elif value == 'USB_CHAINED':
                settings.serialMode = uscSerialMode.SERIAL_MODE_USB_CHAINED
            else:
                settings.serialMode = uscSerialMode.SERIAL_MODE_UART_DETECT_BAUD_RATE

        if FixedBaudRate is not None:
            value = parseInt(FixedBaudRate.text, 'u32')

            if value is not None:
                settings.fixedBaudRate = value
            else:
                warnings.append('Error in value of FixedBaudRate. Skipping.')

        if SerialTimeout is not None:
            value = parseInt(SerialTimeout.text, 'u16')

            if value is not None:
                settings.serialTimeout = value
            else:
                warnings.append('Error in value of SerialTimeout. Skipping.')

        if EnableCrc is not None:
            value = parseBool(EnableCrc.text)

            if value is not None:
                settings.enableCrc = value
            else:
                warnings.append('Error in value of EnableCrc. Skipping.')

        if SerialDeviceNumber is not None:
            value = parseInt(SerialDeviceNumber.text, 'u8')

            if value is not None:
                settings.serialDeviceNumber = value
            else:
                warnings.append('Error in value of SerialDeviceNumber. Skipping.')

        if SerialMiniSscOffset is not None:
            value = parseInt(SerialMiniSscOffset.text, 'u8')

            if value is not None:
                settings.miniSscOffset = value
            else:
                warnings.append('Error in value of SerialMiniSscOffset. Skipping.')

        if ServosAvailable is not None:
            value = parseInt(ServosAvailable.text, 'u8')

            if value is not None:
                settings.servosAvailable = value
            else:
                warnings.append('Error in value of ServosAvailable. Skipping.')

        if ServoPeriod is not None:
            value = parseInt(ServoPeriod.text, 'u8')

            if value is not None:
                settings.servoPeriod = value
            else:
                warnings.append('Error in value of ServoPeriod. Skipping.')

        if EnablePullups is not None:
            value = parseBool(EnablePullups.text)

            if value is not None:
                settings.enablePullups = value
            else:
                warnings.append('Error in value of EnablePullups. Skipping.')

        if MiniMaestroServoPeriod is not None:
            value = parseInt(MiniMaestroServoPeriod.text, 'u32')

            if value is not None:
                settings.miniMaestroServoPeriod = value
            else:
                warnings.append('Error in value of MiniMaestroServoPeriod. Skipping.')

        if ServoMultiplier is not None:
            value = parseInt(ServoMultiplier.text, 'u16')

            if value is not None:
                settings.servoMultiplier = value
            else:
                warnings.append('Error in value of ServoMultiplier. Skipping.')

        return warnings

    @staticmethod
    def save(settings, file):
        raise NotImplementedError
