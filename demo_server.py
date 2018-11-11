# coding:utf-8

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

