# coding:utf-8
# ネットワーク側にpingが出来ない、もしくは、websocketでセンサーデータを受けない期間がある一定時間になるとリブート
import pings
import time
import subprocess
import websocket
import threading
from datetime import datetime

sensor_event        = "washing_sensor"

ping_addr           = "google.com" # Ping先IPアドレス
start_wait_time     = 10           # WebSocketサーバ開始待ち(s)
reboot_time         = 120          # 左記の秒数常時異常検知であれば再起動(s)  pingとwebsocetデータ受信

ping_retry_count    = 0
websock_retry_count = 0




class ChkWebSock():
    connect = False
    last_rcv_time = time.time()

    def on_message(self, message):
        print message
        websock_retry_count = 0
        self.last_rcv_time = time.time()

    def on_error(self, error):
        print error
    
    def on_close(self):
        print 'disconnected streaming server'
        self.connect = False
        
    
    def on_open(self):
        print 'connected streaming server'
        self.connect = True
        self.ws.send("type:subscribe\tdata:"+sensor_event)

    def __init__(self, url):
        websocket.enableTrace(True)
        self.ws = websocket.WebSocketApp(url,
                                header=[
                                        "x-retry-count: 0"
                                       ],
                                on_open=self.on_open,
                                on_message=self.on_message,
                                on_error=self.on_error,
                                on_close=self.on_close)

    def ws_start(self):
        self.ws.run_forever()

    def ws_stop(self):
        self.ws.close()
        

def chk_ping(p):
    global ping_retry_count

    if ping_addr != "":
        res = p.ping(ping_addr)

        if res.is_reached():
            # 監視対象への接続ができた
            #do_something()
            print "ping OK"
            ping_retry_count = 0
        else:
            # 監視対象への接続ができなかった
            #do_something()
            print "ping NG"
            ping_retry_count = ping_retry_count + 1

        if ping_retry_count >= reboot_time / 10:
            print "ping timeout"
            print_str = datetime.now().strftime("%Y%m%d_%H%M%S.%f")
            str = subprocess.call("/bin/echo 1 > /root/ping_error"+print_str+".txt", shell=True)
            str = subprocess.call("/sbin/reboot", shell=True)

        res.print_messages()


t1 = None
def chk_websocket(chkwebsock):
    global websock_retry_count
    global t1

    if chkwebsock.connect == False:
        if t1 != None:
            #chkwebsock.ws.stop()
            t1.join()
        t1 = threading.Thread(target=chkwebsock.ws_start)
        t1.start()
        websock_retry_count = websock_retry_count + 1
    
    now = time.time()
    if (now - chkwebsock.last_rcv_time) >= reboot_time:
        print "websocket timeout"
        print_str = datetime.now().strftime("%Y%m%d_%H%M%S.%f")
        str = subprocess.call("/bin/echo 1 > /root/websocket_error"+print_str+".txt", shell=True)
        str = subprocess.call("/sbin/reboot", shell=True)




def main():
    print "waiting websocket starting"
    time.sleep(start_wait_time)

    p = pings.Ping()

    url = "ws://127.0.0.1:8080/"
    chkwebsock = ChkWebSock(url)

    try:
        while 1:
            # ping確認
            chk_ping(p)

            # websocket確認
            chk_websocket(chkwebsock)
            
            time.sleep(10)
            
    except KeyboardInterrupt:
        chkwebsock.ws_stop()



if __name__ == '__main__':
    main()

