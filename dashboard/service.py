import os
from threading import Event

from weavelib.services import BasePlugin, MessagingEnabled

from dashboard.modules import RPCModule, StaticFileModule
from dashboard.http import WeaveHTTPServer

class DashboardService(MessagingEnabled, BasePlugin):
    def __init__(self, *args, **kwargs):
        super(DashboardService, self).__init__(*args, **kwargs)

        self.static_module = StaticFileModule(self)
        modules = [
            ("/rpc", RPCModule(self)),
            ("/static", self.static_module),
        ]
        self.http = WeaveHTTPServer(self, modules)
        self.exited = Event()

    def on_service_start(self, *args, **kwargs):
        base_path = './static'
        for root, _, files in os.walk(base_path):
            for filename in files:
                full_path = os.path.join(root, filename)
                rel_path = full_path[len(base_path):]
                with open(full_path, 'rb') as inp:
                    content = inp.read()
                self.static_module.write_file(rel_path.lstrip('/'), content)

        self.http.start()
        self.notify_start()
        self.exited.wait()

    def on_service_stop(self, *args, **kwargs):
        self.http.stop()
        self.exited.set()
