# coding:utf-8
import threading
import time
import re
import urllib2
import json
#import ConfigParser
from datetime import datetime
import json
import sys
import serial
import RPi.GPIO as GPIO
import binascii

# websocketサーバ
import tornado.web
import tornado.httpserver
import tornado.websocket
from tornado.concurrent import is_future
import threading
from tornado import gen
import traceback
from tornado.web import url
try:
    import asyncio
    # Python 3
except ImportError:
    asyncio = None
    # Python 2
try:
    raw_input
    # Python 2
except NameError as e:
    raw_input = input
    # Python 3


###################################################################
###################################################################
# 全体(WiFi関連・デバッグポート)
#     デバッグポートが一定期間センサーデータが上がってきていなければ
#     切断したと判断し、再接続処理を行う。
#     デバッグポート再接続完了時に、WiFiの起動シーケンスを行う。
###################################################################
###################################################################
wifi_port  = "/dev/ttyAMA0"
debug_port = "/dev/ttyUSB0"
shutdown_time = 300                     # 洗濯機実行して５分で電源OFF

state = "disconnect"
phase = 0
exec_start_time = time.time()

#state = "debug_connecting"
#state = "wifi_connecting"
#state = "connect"
#state = "shutdowning"


###################################################################
###################################################################
# WiFi関連
###################################################################
###################################################################
CONFIG_FILE    = 'CONFIG.ini'
EOJ_CLASS_GRP  = 0x03
EOJ_CLASS_CODE = 0xd3
EOJ_INSTANCE   = 0x01
SSID           = "aterm-9dd259-g"

###################################################################
# pin定義(WiFi)
###################################################################
power_pin = 21

# WiFi⇔マイコン
wifi2micon_enable_pin = 2
micon2wifi_enable_pin = 17
# ラズパイ⇔マイコン
rasp2micon_enable_pin = 4
micon2rasp_enable_pin = 10
# WiFi→ラズパイ
wifi2rasp_enable_pin  = 9

###################################################################
# OutputEnable定義(WiFi)
###################################################################
OE_enable  = 0
OE_disable = 1

###################################################################
# Relay
###################################################################
relay_on  = 0
relay_off = 1


###################################################################
# 家電共通IFVer2.0メッセージ定義
###################################################################
# 家電状態変化通知応答
def rcvMiconState(seq):
    sndmsgbuf = [0x5a]                                                                  # ヘッダー
    sndmsgbuf = sndmsgbuf + [seq]                                                       # シーケンス番号
    sndmsgbuf = sndmsgbuf + [0x10, 0x8a, 0x00, 0x04, 0x00, EOJ_CLASS_GRP, EOJ_CLASS_CODE, EOJ_INSTANCE]
    sum = calc_checksum(sndmsgbuf)
    sndmsgbuf = sndmsgbuf + [sum]
    #print "rcvMiconState:",
    snd_proc(sndmsgbuf)

# 通信媒体状態取得応答
def rcvCommState(seq):
    sndmsgbuf = [0x5a]                                                                  # ヘッダー
    sndmsgbuf = sndmsgbuf + [seq]                                                       # シーケンス番号
    sndmsgbuf = sndmsgbuf + [0x01, 0x81, 0x00, 0x03, 0x00, 0x11, 0x13]
    sum = calc_checksum(sndmsgbuf)
    sndmsgbuf = sndmsgbuf + [sum]
    #print "rcvCommState:",
    snd_proc(sndmsgbuf)

# 無線LAN設定確認応答
def rcvWiFiConfirm(seq):
    '''
    sndmsgbuf = [0x5a]                                                                  # ヘッダー
    sndmsgbuf = sndmsgbuf + [seq]                                                       # シーケンス番号
    sndmsgbuf = sndmsgbuf + [0x01, 0xc2, 0x00, 0x15, 0x00, 0x01, 0x0e, 0x61, 0x74, 0x65, 0x72, 0x6d, 0x2d, 0x39, 0x64, 0x64, 0x32, 0x35, 0x39, 0x2d, 0x67, 0x00, 0x22, 0x00, 0x0c]
    sum = calc_checksum(sndmsgbuf)
    sndmsgbuf = sndmsgbuf + [sum]
    snd_proc(sndmsgbuf)
    '''
    sndmsgbuf = [0x5a]                                                                  # ヘッダー
    sndmsgbuf = sndmsgbuf + [seq]                                                       # シーケンス番号
    sndmsgbuf = sndmsgbuf + [0x01]                                                      # 通信タイプ(0x01:遠隔操作)
    sndmsgbuf = sndmsgbuf + [0xc2]                                                      # 処理コード(0xc2:無線LAN設定確認応答
                                                                                        # データ長2byte
    sndmsgbuf_tmp = []
    sndmsgbuf_tmp = sndmsgbuf_tmp + [0x00]                                              # 処理結果(0x00:成功)
    sndmsgbuf_tmp = sndmsgbuf_tmp + [0x01]                                              # 無線LAN設定状況(0x01:設定有)
    sndmsgbuf_tmp = sndmsgbuf_tmp + [len(SSID)]                                         # SSIDの長さ
    for i in range(0, len(SSID)):                                                       # SSID
        sndmsgbuf_tmp.extend([ord(SSID[i])])                                            # 
    sndmsgbuf_tmp = sndmsgbuf_tmp + [0x00, 0x22, 0x00, 0x0C]                            # 認証・暗号タイプ(0022 000C:WPA/WPA2-PSK)
    
    setShort(sndmsgbuf, len(sndmsgbuf_tmp))
    sndmsgbuf = sndmsgbuf + sndmsgbuf_tmp

    sum = calc_checksum(sndmsgbuf)
    sndmsgbuf = sndmsgbuf + [sum]
    #print "rcvWiFiConfirm:",
    snd_proc(sndmsgbuf)
    '''
    sndmsgbuf = ''.join(' 0x'+format(x, '02x') for x in sndmsgbuf)
    sndmsgbuf = "[" + sndmsgbuf + "]"
    sndmsgbuf = sndmsgbuf.replace("[ ", "['")
    sndmsgbuf = sndmsgbuf.replace(" ", "', '")
    sndmsgbuf = sndmsgbuf.replace("]", "']")
    print "アダプタ→家電: 無線LAN設定確認応答: " + sndmsgbuf
    '''


# Open応答
def rcvOpenReq(seq):
    sndmsgbuf = [0x5a]                                                                  # ヘッダー
    sndmsgbuf = sndmsgbuf + [seq]                                                       # シーケンス番号
    sndmsgbuf = sndmsgbuf + [0x11, 0x81, 0x00, 0x01, 0x00]
    sum = calc_checksum(sndmsgbuf)
    sndmsgbuf = sndmsgbuf + [sum]
    #print "rcvOpenReq:",
    snd_proc(sndmsgbuf)

# Flush応答
def rcvFlashReq(seq):
    try:
        sndmsgbuf = [0x5a]                                                                  # ヘッダー
        sndmsgbuf = sndmsgbuf + [seq]                                                       # シーケンス番号
        sndmsgbuf = sndmsgbuf + [0x11, 0x84, 0x00, 0x01, 0x00]
        sum = calc_checksum(sndmsgbuf)
        sndmsgbuf = sndmsgbuf + [sum]
        #print "rcvFlashReq:",
        snd_proc(sndmsgbuf)
    except:
        print "cannot res FlashReq"


###################################################################
# 変数
###################################################################
starting_snd_seqno = 0                                                                  # 起動シーケンス送信番号
starting_rcv_seqno = 0                                                                  # 起動シーケンス受信番号

waiting_rcv_id = 0                                                                      # 受信待ちID
rcv_id = 0                                                                              # 受信したID

seqno = 0                                                                               # 送信シーケンス番号
rcv_seqno = 0                                                                           # 受信シーケンス番号
lastrcv_time = time.time()                                                              # 最終受信時刻

###################################################################
# WiFi起動シーケンス初期化
###################################################################
def init_wifi_seq():
    global starting_snd_seqno                                                           # 起動シーケンス送信番号
    global starting_rcv_seqno                                                           # 起動シーケンス受信番号
    global waiting_rcv_id                                                               # 受信待ちID
    global rcv_id                                                                       # 受信したID
    global seqno                                                                        # 送信シーケンス番号
    global rcv_seqno                                                                    # 受信シーケンス番号
    global lastrcv_time                                                                 # 最終受信時刻
    global last_ok_time

    starting_snd_seqno = 0                                                              # 起動シーケンス送信番号
    starting_rcv_seqno = 0                                                              # 起動シーケンス受信番号
    waiting_rcv_id = 0                                                                  # 受信待ちID
    rcv_id = 0                                                                          # 受信したID
    seqno = 0                                                                           # 送信シーケンス番号
    rcv_seqno = 0                                                                       # 受信シーケンス番号
    lastrcv_time = time.time()                                                          # 最終受信時刻
    last_ok_time = lastrcv_time                                                          # 最終受信時刻
    


###################################################################
# シリアルバイナリデータ変換
#   入力： バイナリデータ配列
###################################################################
def a2s(arr):
    """ Array of integer byte values --> binary string
    """
    return ''.join(chr(b) for b in arr)


###################################################################
# 2バイト設定
#   入力： バイナリデータ配列
#   入力： 値
###################################################################
def setShort(array, value):
    tmp1 = [(int(value) >> 8) & 0xff]
    tmp2 = [int(value) & 0xff]
    array.extend(tmp1)
    array.extend(tmp2)


###################################################################
# シーケンス番号取得
###################################################################
def getSeqno():
    global seqno
    ret_seq = seqno
    seqno = seqno + 1
    return ret_seq




###################################################################
# 家電コマンド制御要求（遠隔）実行
###################################################################
def exec_custom(sndindex):
    global seqno
    seqno = 0

    sndmsgbuf = [0x5a]                                                                  # ヘッダー
    sndmsgbuf = sndmsgbuf + [0x01]                                                      # シーケンス番号
    sndmsgbuf = sndmsgbuf + wifi2micon_msg[sndindex]
    sum = calc_checksum(sndmsgbuf)
    sndmsgbuf = sndmsgbuf + [sum]
    #print "exec_custom:",
    snd_proc(sndmsgbuf)



###################################################################
# チェックサム計算
###################################################################
def calc_checksum(msg):
    sum = 0
    for i in range(0, len(msg)):
        sum = sum + msg[i]
    
    sum = sum & 0xFF
    sum = 256 - sum
    return sum


def exec_washing():
    global exec_start_time
    exec_start_time = time.time()
    power_btn()
    time.sleep(6)
    exec_custom(0)


###################################################################
# キー入力受付
###################################################################
def get_key():
    global server
    
    try:
        c = sys.stdin.read(1)
        if c == '0':
            exec_custom(0)
        if c == '1':
            exec_custom(1)
        if c == '2':
            #exec_custom(2)
            exec_washing()
        elif c == '3':
            server.emit_event("door_opened", "")
        elif c == 'p':
            power_btn()

        t = threading.Timer(0.5, get_key)
        t.start()
    except KeyboardInterrupt:
        sys.exit()
    
    #return c


###################################################################
# 送信メッセージ（送信メッセージ表示）
###################################################################
def snd_proc(sndmsgbuf):
    global state

    if state == "shutdowning":
        return
    
    rcvmsg = ''.join(' 0x'+format(x, '02x') for x in sndmsgbuf)
    rcvmsg = "[" + rcvmsg + "]"
    rcvmsg = rcvmsg.replace("[ ", "['")
    rcvmsg = rcvmsg.replace(" ", "', '")
    rcvmsg = rcvmsg.replace("]", "']")
    ser.write(a2s(sndmsgbuf))
    rcv_comm_type = sndmsgbuf[2]
    rcv_proc_code = sndmsgbuf[3]
    print_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S.%f")
    print print_str,
    print "snd:", proc_code[rcv_comm_type][rcv_proc_code]["dirc"].decode("string-escape") + ": " + proc_code[rcv_comm_type][rcv_proc_code]["name"].decode("string-escape") + ": " + str(rcvmsg)



###################################################################
# 受信メッセージ（受信メッセージ表示）
###################################################################
rcvmsg = []
octet  = 0
msglen = 0
rcv_comm_type = 0
rcv_proc_code = 0
def rcv_proc(rcvdata):
    global rcvmsg
    global octet
    global msglen
    global rcv_comm_type
    global rcv_proc_code
    global rcv_id
    global rcv_seqno

    #if rcvdata == 0x5A and len(rcvmsg) < (msglen+4):
    #if rcvdata == 0x5A or rcvdata == 0x66:
    if rcvdata == 0x5A:
        rcvmsg = ['0x{:02x}'.format(rcvdata)]
        octet  = 0
        msglen = 0
    else:
        rcvmsg = rcvmsg + ['0x{:02x}'.format(rcvdata)]
        if   octet == 0:
            return
        elif octet == 1:
            rcv_seqno = rcvdata
        elif octet == 2:
            rcv_comm_type = rcvdata
        elif octet == 3:
            rcv_proc_code = rcvdata
        elif octet == 4:
            msglen = rcvdata * 256
        elif octet == 5:
            msglen = msglen + rcvdata

    octet = octet + 1
    if octet >= (6 + msglen + 1):
        print_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S.%f")
        print print_str,
        print "rcv:", proc_code[rcv_comm_type][rcv_proc_code]["dirc"].decode("string-escape") + ": " + proc_code[rcv_comm_type][rcv_proc_code]["name"].decode("string-escape") + ": " + str(rcvmsg)
        if proc_code[rcv_comm_type][rcv_proc_code]["proc"] != None:
            proc_code[rcv_comm_type][rcv_proc_code]["proc"](rcv_seqno)
        octet = 0
        """
        try:
            print proc_code[rcv_comm_type][rcv_proc_code]["dirc"].decode("string-escape") + ": " + proc_code[rcv_comm_type][rcv_proc_code]["name"].decode("string-escape") + ": " + str(rcvmsg)
            if proc_code[rcv_comm_type][rcv_proc_code]["proc"] != None:
                proc_code[rcv_comm_type][rcv_proc_code]["proc"](rcv_seqno)
        except:
            print "comm_type = " + '0x{:02x}'.format(rcv_comm_type) + ", proc_code = " + '0x{:02x}'.format(rcv_proc_code) + ": " + str(rcvmsg)
        """
        rcv_id =  rcv_comm_type*256 + rcv_proc_code





###################################################################
# listに依存したデータ読み込み
###################################################################
def read_packet(list):
    global state
    global server
    global phase

    list_length = len(list)
    count = 0
    
    # センサー系
    ser_sensor = serial.Serial(debug_port, 38400, parity = serial.PARITY_EVEN, timeout=0.3)
    ser_sensor.write(a2s(mode))
    state = "debug_connecting"
    print state
    
    while 1:
        ###################################################################
        # パケットの先頭抽出
        ###################################################################
        print "starting packet detect"
        while 1:
            try:
                data = int(sensor_read(ser_sensor), 16)
                #print data
                if data == list[list_length - 2][0]:
                    for i in range(1, 17):
                        sensor_read(ser_sensor)

                    data = int(sensor_read(ser_sensor), 16)
                    if data == list[list_length - 1][0]:
                        for i in range(1, 17):
                            sensor_read(ser_sensor)
                        break
            except:
                ser_sensor.close()
                state = "disconnect"
                print state

                data = {
                    'phase': '-',
                    'remain_min': '-',
                    'rpm': '-',
                    'kgm': '-'
                }
                phase = 0
                server.emit_event("washing_sensor", json.dumps(data))

                time.sleep(0.5)
                ser_sensor = serial.Serial(debug_port, 38400, parity = serial.PARITY_EVEN, timeout=0.3)
                ser_sensor.write(a2s(mode))
                state = "debug_connecting"
                print state

        print "starting read sensor"

        ###################################################################
        # データ読み取り
        ###################################################################
        while 1:
            try:
                count = 0
                for i in list:
                    # データカウンタ
                    data_count = int(sensor_read(ser_sensor), 16)
                    #print "データカウンタ:" + str(data_count)
                    # データ1
                    data1 = int(sensor_read(ser_sensor), 16)
                    data1 = data1 * 255 + int(sensor_read(ser_sensor), 16)
                    list[count][2] = data1
                    #print i[1] + ": " + str(data1)
                    # データ2
                    data2 = int(sensor_read(ser_sensor), 16)
                    data2 = data2 * 255 + int(sensor_read(ser_sensor), 16)
                    list[count][4] = data2
                    #print i[3] + ": " + str(data2)
                    # 残りのデータ
                    for i in range(6, 18):
                        sensor_read(ser_sensor)
                    count = count + 1
            except:
                print_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S.%f")
                print print_str,
                print ": cannot read"
                data = {
                    'phase': '-',
                    'remain_min': '-',
                    'rpm': '-',
                    'kgm': '-'
                }
                phase = 0
                server.emit_event("washing_sensor", json.dumps(data))
                break

            print_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S.%f")
            print print_str,
            print "phase = ", list[6][4],          # 小工程(0 :(初期排水)、1 :布量判定、2 :給水工程、3 :撹拌工程、4 :消泡工程、5 :排水工程、6 :間欠脱水工程、7 :脱水工程、8 :惰性工程、9 :布ほぐし撹拌工程、10:乾燥工程、11:送風工程、12:リント回収工程、13:第2空冷工程、14:ふんわりキープ工程、15:冷却工程)
            print ", remain_min = ", str(list[5][2]),          # 残時間 [min]
            print ", rpm = ", str(list[3][2]),          # 現在回転数 [r/min]
            print ", kgm = ", str(list[20][4])          # 布量センサ 判定値 [kgm^2]
            data = {
                'phase': str(list[6][4]),
                'remain_min': str(list[5][2]),
                'rpm': str(list[3][2]),
                'kgm': str(list[20][4])
            }
            phase = int(list[6][4])
            #data = "3"
            server.emit_event("washing_sensor", json.dumps(data))
            if state == "debug_connecting":
                state = "wifi_connecting"
                print state



                                                                 


def _arg_parser():
    from argparse import ArgumentParser

    usage = ' python {} [--bind_host ADDR] [--bind_port port] [--help]' \
        .format(__file__)
    argparser = ArgumentParser(usage=usage)
    argparser.add_argument('--bind_host', type=str,
                           default="0.0.0.0",
                           help='bind address')
    argparser.add_argument('--bind_port', type=int,
                           default="8080",
                           help='bind port')
    return argparser.parse_args()


###################################################################
# WebSocketのコマンド受付
###################################################################
def _handler(data):
    global state

    print "requested:", data
    dic = json.loads(data)
    if dic["api"] == "washing_exec":
        if dic["status"] == "exec":
            if state == "disconnect" or state == "debug_connecting":
                #print dic["param"]
                #exec_custom(2)
                t = threading.Thread(target=exec_washing)
                t.start()
        if dic["status"] == "off":
            if state != "disconnect" and state != "debug_connecting":
                power_btn()

        return 0
    return -1

def _dummy_temparture_thread():
    import random

    global server

    while True:
        data = {
            'phase': str(random.uniform(10, 50)),
            'remain_min': str(random.uniform(10, 50)),
            'rpm': str(random.uniform(10, 50)),
            'kgm': str(random.uniform(10, 50))
        }
        server.emit_event("washing_sensor", json.dumps(data))
        print "sensor:", data
        time.sleep(10)




###################################################################
# 
###################################################################
def main():
    import json

    global state
    global ser
    global lastrcv_time
    global exec_start_time
    global server

    #Setting
    #config = ConfigParser.ConfigParser()
    #config.read(CONFIG_FILE)
    #url = config.get('PCPF', 'url')
    #deviceGuid = config.get('PCPF', 'DeviceGuid')
    #cycle = config.get('PCPF', 'Cycle')
   
    #pdp = PDP.PdpUtil(url, deviceGuid, cb_cmd)
    #t1 = threading.Thread(target=pdp.ws_start)
    #t1.start()




    
    ###################################################################
    # キー入力受付スレッド
    ###################################################################
    t = threading.Thread(target=get_key)
    t.start()
    
    
    args = _arg_parser()
    server = APConnectorServer(bind_host=args.bind_host, bind_port=args.bind_port)
    server.set_request_handler(_handler)
    server.start()

    #t3 = threading.Thread(target=_dummy_temparture_thread)
    #t3.daemon = True
    #t3.start()



class ConnectionHandler(tornado.websocket.WebSocketHandler):
    subscribers = {}
    request_handler = {}

    def open(self, *args, **kwargs):
        print "connection opened from client"

    @gen.coroutine
    def on_message(self, message):
        print "on_message:", message
        try:
            dic = {}
            # LTSVのパース
            for field in message.split("\t"):
                kv = field.split(":", 1)
                if len(kv) <= 1:
                    continue
                dic[kv[0]] = kv[1]

            # requestの場合
            if dic["type"] == "req":
                if "callback" in ConnectionHandler.request_handler:
                    result = ConnectionHandler.call_request_handler(dic["data"])
                    if is_future(result):
                        result = yield result
                    print "response:" + str(result)
                    self.send_response(dic["id"], result)

            if dic["type"] == "subscribe":
                connections = self.subscribers.get(dic["data"], None)
                if connections == None:
                    connections = set()
                    self.subscribers[dic["data"]] = connections
                connections.add(self)

            if dic["type"] == "unsubscribe":
                connections = self.subscribers.get(dic["data"], [])
                connections.discard(self)

        except Exception as e:
            print e
            print traceback.format_exc()

    def on_close(self):
        print "connection closed"
        try:
            for k, connections in self.subscribers.items():
                connections.discard(self)
        except Exception as e:
            print e

    @classmethod
    def emit_event(cls, event, data):
        #print "sent event:", event
        for connection in cls.subscribers.get(event, []):
            connection.write_message("type:event\tevent:%s\tdata:%s" % (event, data))

    def send_response(self, id, data):
        self.write_message("type:res\tid:%s\tdata:%s" % (id, data))

    @classmethod
    def set_request_handler(cls, callback):
        cls.request_handler["callback"] = callback

    @classmethod
    def call_request_handler(cls, data):
        return cls.request_handler["callback"](data)

class APConnectorServer:
    def __init__(self, bind_host = "0.0.0.0", bind_port = 8080, root_path = "/"):
        self.__bind_host = bind_host
        self.__bind_port = bind_port
        self.__root_path = root_path
        self.__io_loop = None

    def start(self, daemon=True):
        t = threading.Thread(target=self._run)
        t.daemon = daemon
        t.start()

    def _run(self):
        if asyncio is not None:
            asyncio.set_event_loop(asyncio.new_event_loop())
        rt = tornado.web.Application([
            url(self.__root_path, ConnectionHandler)
        ], debug=True)
        http_server = tornado.httpserver.HTTPServer(rt)
        http_server.listen(self.__bind_port, self.__bind_host)
        self.__io_loop = tornado.ioloop.IOLoop.instance()
        self.__io_loop.start()

    def emit_event(self, event, data):
        if self.__io_loop is not None:
            self.__io_loop.add_callback(ConnectionHandler.emit_event, event, data)

    def set_request_handler(self, callback):
        ConnectionHandler.set_request_handler(callback)




if __name__ == '__main__':
    main()

