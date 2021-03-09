import unicodedata
from pprint import pformat
from ppadb.client import Client as AdbClient
from framework.configs.slotInfo import slotInfo
from framework import api
from framework.model.utility.FileService import FileService
from datetime import datetime, timedelta 




class safeAdbClient:
    def __init__(self, host=None, port=None, verbose=False):
        self._verbose = verbose
        self._adbClient = AdbClient(host=host, port=port)
        self._log("ADBClient: Initializing service to server {}:{}".format(host, port))

    @staticmethod
    def _log(message):
        api.writeDebugLine(message)

    def get_serials(self):
        devices = []
        try:
            devices = self._adbClient.devices(state='device')
        except Exception as e:
            self._log('ADBClient: Exception: {}'.format(str(e)))
        serials =[device.serial for device in devices]
        if self._verbose:
            self._log('ADBClient: INFO: Reading devices = \n' + str(sorted(serials)))
        else:
            self._log('ADBClient: INFO: Reading {} devices'.format(len(serials)))
        return serials

    def remote_connect(self, ip, port, retry=2):
        result = None
        count = 0
        while count < retry:
            if self._verbose:
                self._log("ADBClient: INFO: Try {}/{} connecting to '{}:{}'".format(count+1, retry, ip, str(port)))
            try:
                result = self._adbClient.remote_connect(ip, port)
            except Exception as e:
                self._log('ADBClient: Exception: {}'.format(str(e)))
                count += 1
            else:
                count = retry
        return result

    def device_shell(self, serial, cmd, message, retry=2, **kwargs):
        count = 0
        while count < retry:
            if self._verbose:
                self._log("ADBClient: INFO: Try {}/{} running shell command '{}'".format(count+1, retry, cmd))
            try:
                self._adbClient.device(serial).shell(cmd, **kwargs)
                self._log(message)
                count = retry
            except RuntimeError:
                self._log("ADBClient: ERROR: Could not connect to Device: Device '{}' may be switched OFF".format(serial))
            count += 1

    def get_host(self):
        return self._adbClient.host


class ADBLogs:
    KEYMAP = {
            "353":"OK",
            "103":"Up",
            "108":"Down",
            "105":"Left",
            "106":"Right",
            "172":"MENU",
            "158":"Back",
            "580":"APPS",
            "362":"TV-Guide",
            "11":"0",
            "2":"1",
            "3":"2",
            "4":"3",
            "5":"4",
            "6":"5",
            "7":"6",
            "8":"7",
            "9":"8",
            "10":"9",
            "113":"Mute",
            "114":"VolumeDown",
            "115":"VolumeUp",
            "165":"Rewind",
            "163":"Forward",
            "164":"Play",
            "167":"Record",
            "128":"STOP",
            "116":"Power"
        }

    def __init__(self, host='10.13.130.171', port=5039, verbose=False):
        self.verbose = verbose
        self.adbClient = safeAdbClient(host=host, port=port, verbose=verbose)
        self.deviceList = self.adbClient.get_serials()
        self.logs = []
        self.startTime = None

    def setStartTime(self, time):
        self.startTime = time

    def getSlotsConnected(self, server):
        slots = []
        for slotNo in range(16):
            serial = self.createDeviceSerial(server, slotNo+1)
            if self.deviceExists(serial):
                slots.append(slotNo+1)
        return slots

    def attemptConnect(self, server, slotNo, port=5555):
        ip = slotInfo[server][str(slotNo)]["ip"]
        serial = self.createDeviceSerial(server, slotNo)
        if not self.deviceExists(serial):
            api.writeDebugLine("ADBLog: WARNING: The slot '{}' seems not to be connected to the ADB server on {}"
                .format(slotNo, self.adbClient.get_host()))
        connected = self.adbClient.remote_connect(ip, port)
        if connected and not self.deviceExists(serial):
            self.deviceList.append(serial)
        return serial if connected else None

    def dumpLogCat(self, connection):
        while True:
            data = connection.read(4096)
            if not data:
                break
            # self.logs.extend(data.decode('utf-8').split('\n'))
            try:
                self.logs.append(data.decode('utf-8'))
            except:
                print("Some unicode issue detected while loading the ADB logs")
                self.logs.append(str(data).encode('utf-8').decode('utf-8'))
                # unicodedata.normalize('NFKD', data).encode('ascii', 'ignore')
            # print(data.decode('utf-8'))
        connection.close()

    @staticmethod
    def createDeviceSerial(server, slotNo):
        return slotInfo[server][str(slotNo)]["ip"]+":5555"

    def deviceExists(self, serial):
        return serial in self.deviceList

    def _runDeviceShell(self, server, slotNo, cmd, message, region, clear_logs=True, **kwargs):
        if region:
            api.beginLogRegion(region)

        if clear_logs:
            self.logs = []

        serial = self.attemptConnect(server, slotNo)
        if serial:
            self.adbClient.device_shell(serial, cmd, message, **kwargs)

        if region:
            api.endLogRegion(region)

    def clearLogCat(self, server, slotNo, region="ADB Logs"):
        message = "ADBLog: The logcat is now cleared"
        cmd = "logcat -c"
        self._runDeviceShell(server, slotNo, cmd, message, region)
        return self.logs

    def _getStartTimestamp(self, limit=timedelta(minutes=5), timestamp_format='%m-%d %H:%M:%S'):
        if self.startTime is None:
            d = datetime.today() - limit
            return d.strftime(timestamp_format)
        else:
            return self.startTime.strftime(timestamp_format)

    def getLogs(self, server, slotNo, search=None, region=None):
        if search is None:
            search = 'emit key release:'
        message = "ADBLog: Requested logs received"
        cmd = "logcat -v time -v printable -t '{}.000' -d UEI.BLE:D NexusIR:I -e '{}'".format(self._getStartTimestamp(), search)
        # cmd = "logcat -v time -d UEI.BLE:D NexusIR:I -e '{}'".format(search)
        # cmd = 'logcat -v time -d -t "{}.000"'.format(self.startTime.strftime('%m-%d %H:%M:%S'))
        # cmd = "logcat -v time -d UEI.BLE:D NexusIR:I *:S"
        self._runDeviceShell(server, slotNo, cmd, message, region, handler=self.dumpLogCat)
        return self.logs

    def getGenericLogs(self, server, slotNo, tag=None, search=None, region=None, limit=timedelta(minutes=5), timeLimited=True):
        message = "ADBLog: Requested logs received"
        cmd = "logcat -v time -v printable -d '{}' -e '{}'"
        if isinstance(limit, timedelta):
            if timeLimited:
                cmd = "logcat -v time -v printable -t '{}.000' -d '{}' -e '{}'".format(self._getStartTimestamp(limit), tag, search)
            else:
                cmd = "logcat -v time -v printable -d '{}' -e '{}'".format(tag, search)
        elif isinstance(limit, int):
            if timeLimited:
                cmd = "logcat -v time -v printable -t '{}' -d '{}' -e '{}'".format(str(limit), tag, search)
            else:
                cmd = "logcat -v time -v printable -d '{}' -e '{}'".format(tag, search)
        else:
            api.writeDebugLine('ADBLog: WARNING: Unknown limit type({}). Reading all logs.'.format(type(limit)))
        # cmd = "logcat -v time -d UEI.BLE:D NexusIR:I -e '{}'".format(search)
        # cmd = 'logcat -v time -d -t "{}.000"'.format(self.startTime.strftime('%m-%d %H:%M:%S'))
        # cmd = "logcat -v time -d UEI.BLE:D NexusIR:I *:S"
        self._runDeviceShell(server, slotNo, cmd, message, region, handler=self.dumpLogCat)
        return self.logs

    def getAllLogs(self, server, slotNo, region=None, limit=timedelta(minutes=5)):
        message = "ADBLog: Logs received"
        cmd = 'logcat -v time -v printable -d'
        # cmd = "logcat -v time -d UEI.BLE:D NexusIR:I *:S"
        if isinstance(limit, timedelta):
            cmd += ' -T "{}.000"'.format(self._getStartTimestamp(limit))
        elif isinstance(limit, int):
            cmd += ' -T "{}"'.format(str(limit))
        else:
            api.writeDebugLine('ADBLog: WARNING: Unknown limit type({}). Reading all logs.'.format(type(limit)))
        self._runDeviceShell(server, slotNo, cmd, message, region, handler=self.dumpLogCat)
        return self.logs

    def _translateKeys(self, t, s):
        returnString = ""
        leftOverString = ""
        si = 0
        sl = len(s)
        lines = t.split("\n")
        if len(lines) > 1:
            for i in range(len(lines)-1):
                si = lines[i].find(s)
                if si > 0:
                    returnString += lines[i] + " -> " + self.KEYMAP[lines[i][si+sl:].strip()] + "\n"
                else:
                    returnString += lines[i] + "\n"
            leftOverString = lines[len(lines)-1]
        else:
            leftOverString = t
        return returnString, leftOverString

    def printLogs(self, server, slotNo, search=None):
        searchString = "e:"
        # searchString = "emit key release:"
        restOfLog = ""
        api.beginLogRegion("ADB Logs")
        self.getLogs(server, slotNo, search)
        if self.verbose:
            api.writeDebugLine("ADBLog: Searching {} logs for '{}'".format(len(self.logs), search))
        for log in self.logs:
            if search is None:
                logToPrint, restOfLog = self._translateKeys(restOfLog + log, "e:")
                print(logToPrint, end='')
            else:
                print(log, end='')
            # print log, self.keyMap[log[log.find(searchString) + len(searchString) + 1:]],
        api.endLogRegion("ADB Logs")

    def printGenericLogs(self, server, slotNo, tag=None, search=None):
        searchString = "e:"
        # searchString = "emit key release:"
        restOfLog = ""
        api.beginLogRegion("ADB Logs")
        self.getGenericLogs(server, slotNo, tag, search)
        if self.verbose:
            api.writeDebugLine("ADBLog: Searching {} logs for '{}'".format(len(self.logs), search))
        for log in self.logs:
            print(log)
        api.endLogRegion("ADB Logs")
        return

    def printAllLogs(self, server, slotNo, limit=None):
        api.beginLogRegion("ADB Logs")
        self.getAllLogs(server, slotNo, limit=limit)
        if self.logs:
            logToPrint = '\n'.join(self.logs)
            api.writeDebugLine('logs:\n' + logToPrint)
            api.writeDebugLine('ADBLog: Summary: {} log lines'.format(len(self.logs)))
        api.endLogRegion("ADB Logs")

    def saveAllLogs(self, server, slotNo):
        now = datetime.now()
        current_time = now.strftime("%H%M%S")
        kdsn = slotInfo[server][str(slotNo)]["KDSN"]
        filename = 'device{}-{}.log'.format(kdsn, current_time)
        f = FileService(filename=filename)
        api.beginLogRegion("ADB Logs")
        self.getAllLogs(server, slotNo)
        for log in self.logs:
            try:
                f.fileWrite(log)
            except:
                pass
        api.writeDebugLine("ADBLog: Summary: {} log lines saved in file: {}".format(len(self.logs), filename))
        api.endLogRegion("ADB Logs")


if __name__ == "__main__":
    server = "10.13.130.182"
    adbLogs = ADBLogs(verbose=True)
    # for slotNo in range(16):
    #     adbLogs.printLogs(server, slotNo+1, 'power_set_state')
    #     adbLogs.printAllLogs(server, slotNo+1, limit=5)
    # for slotNo in adbLogs.getSlotsConnected(server):
    #     adbLogs.printLogs(server, slotNo)
    # adbLogs.clearLogCat(server, slotNo)
    # adbLogs.clearLogCat(server, 16)
    # adbLogs.saveAllLogs(server, 16)
    for line in adbLogs.getGenericLogs(server, 13, tag="DhcpClient:D", search="ACK"):
        print(line)
