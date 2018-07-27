from threading import Event

from weavelib.http import AppHTTPServer
from weavelib.services import BasePlugin


class DashboardService(BasePlugin):
    def __init__(self, *args, **kwargs):
        super(DashboardService, self).__init__(*args, **kwargs)
        self.http = AppHTTPServer(self)
        self.exited = Event()

    def on_service_start(self, *args, **kwargs):
        self.http.start()
        self.http.register_folder('static')
        self.notify_start()
        self.exited.wait()

    def on_service_stop(self, *args, **kwargs):
        self.http.stop()
        self.exited.set()
