# coding:utf-8
import threading
import time
import re
import urllib2
import json
# websocketサーバ
import tornado.web
import tornado.httpserver
import tornado.websocket
from tornado.concurrent import is_future
import threading
from tornado import gen
import traceback
from tornado.web import url

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
# 
###################################################################
def main():
    import json

    global state
    global ser
    global lastrcv_time
    global exec_start_time
    global server

    
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

