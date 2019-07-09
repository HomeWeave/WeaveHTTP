import json
import logging
import os
from threading import Lock, Thread
from wsgiref.simple_server import make_server, WSGIServer

from bottle import Bottle, ServerAdapter, static_file, request

from weavelib.exceptions import WeaveException


logger = logging.getLogger(__name__)


# From: https://stackoverflow.com/a/16056443/227884
class MyWSGIRefServer(ServerAdapter):
    server = None

    def run(self, handler):
        class CustomWSGIServer(WSGIServer):
            allow_reuse_address = True

        self.options['server_class'] = CustomWSGIServer
        self.server = make_server(self.host, self.port, handler, **self.options)
        self.server.serve_forever()

    def stop(self):
        self.server.server_close()
        self.server.shutdown()


class WeaveHTTPServer(Bottle):
    def __init__(self, service, modules, host="", port=15000):
        super(WeaveHTTPServer, self).__init__()
        self.server = MyWSGIRefServer(host=host, port=port)
        self.thread = Thread(target=self.run, kwargs={"server": self.server})

        self.modules = modules
        for prefix, module in modules:
            for method, path_suffix, callback in module.get_registrations():
                path = os.path.join(prefix, path_suffix)
                logger.info("Registering: %s at %s", callback, path)
                func = self.handle_api(module, method, callback)
                self.route(path, method)(func)

    def start(self):
        for _, module in self.modules:
            module.start()
        self.thread.start()

    def stop(self):
        self.server.stop()
        self.thread.join()
        for _, modules in self.modules:
            modules.stop()

    def handle_api(self, module, method, callback):
        def process_request(*args, **kwargs):
            if method == "POST":
                params = json.load(request.body)
            elif method == "GET":
                params = request.query
            try:
                result = callback(params, *args, **kwargs)
                return module.transform_response(200, result)
            except WeaveException as e:
                logger.exception("WeaveException occured.")
                return module.transform_response(400,
                                                 e.err_msg() + ": " + e.extra)
            except Exception:
                logger.exception("Internal server error.")
                return module.transform_response(500, "Error has been logged.")
        return process_request
