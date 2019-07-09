import os
import time
from contextlib import contextmanager
from threading import Thread

import requests

from weavelib.exceptions import ObjectNotFound
from weavelib.messaging import WeaveConnection
from weavelib.rpc import find_rpc, ServerAPI, ArgParameter, RPCClient, RPCServer
from weavelib.services import BackgroundThreadServiceStart, MessagingEnabled
from weavelib.services import BaseService

from dashboard.service import DashboardService

from test_utils import MessagingService, DummyEnvService


MESSAGING_PLUGIN_URL = "https://github.com/HomeWeave/WeaveServer.git"


class ThreadedDashboardService(BackgroundThreadServiceStart, DashboardService):
    pass


class DummyService(MessagingEnabled, BaseService):
    def __init__(self, conn, token):
        super(DummyService, self).__init__(auth_token=token, conn=conn)
        apis = [
            ServerAPI("api", "desc1", [
                ArgParameter("param", "d1", str),
            ], self.api),
            ServerAPI("number", "desc1", [
                ArgParameter("param", "d1", int),
            ], self.number),
            ServerAPI("exception", "desc1", [], self.exception),
        ]
        self.rpc_server = RPCServer("name", "desc", apis, self)

    def number(self, param):
        return param + 1

    def api(self, param):
        return "API" + param

    def exception(self):
        raise ObjectNotFound("blah")

    def on_service_start(self):
        self.rpc_server.start()

    def on_service_stop(self):
        self.rpc_server.stop()


class TestDashboardService(object):
    @classmethod
    def setup_class(cls):
        cls.messaging_service = MessagingService()
        cls.messaging_service.service_start()
        cls.messaging_service.wait_for_start(15)

        cls.conn = WeaveConnection.local()
        cls.conn.connect()

        cls.env_service = DummyEnvService(cls.messaging_service.test_token,
                                          cls.conn)

        rpc_info = find_rpc(cls.env_service, MESSAGING_PLUGIN_URL,
                            "app_manager")
        appmgr_client = RPCClient(cls.env_service.get_connection(), rpc_info,
                                  cls.env_service.get_auth_token())
        appmgr_client.start()

        # Register the DummyService used in the test cases.
        test_token = appmgr_client["register_plugin"]("a", "b", _block=True)

        dummy_token = appmgr_client["register_plugin"]("x", "y", _block=True)

        appmgr_client.stop()

        cls.dummy_service = DummyService(cls.conn, dummy_token)
        cls.dummy_service.service_start()
        cls.dummy_service.wait_for_start(15)

        cls.service = ThreadedDashboardService(auth_token=test_token,
                                               plugin_dir="x", venv_dir="y",
                                               conn=cls.conn, started_token="t")
        cls.service.service_start()
        cls.service.wait_for_start(15)

    @classmethod
    def teardown_class(cls):
        cls.conn.close()
        cls.service.service_stop()
        cls.dummy_service.service_stop()
        cls.messaging_service.service_stop()

    def test_static_files(self):
        url = "http://localhost:15000/static/index.html"
        response = requests.get(url)
        assert response.status_code == 200

    def test_rpc(self):
        url = "http://localhost:15000/rpc/"
        data = {
            "app_url": "y",
            "rpc_name": "name",
            "api_name": "api",
            "args": ["test"],
        }
        response = requests.post(url, json=data)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "data": "APItest"}

    def test_rpc_api_bad_arguments(self):
        url = "http://localhost:15000/rpc/"
        data = {
            "app_url": "y",
            "rpc_name": "name",
            "api_name": "number",
            "args": ["test"],
        }
        response = requests.post(url, json=data)
        assert response.status_code == 400
        assert response.json()["status"] == "error"
        assert "BadArguments" in response.json()["message"]

    def test_rpc_server_exception(self):
        url = "http://localhost:15000/rpc/"
        data = {
            "app_url": "y",
            "rpc_name": "name",
            "api_name": "exception",
            "args": [],
        }
        response = requests.post(url, json=data)
        assert response.status_code == 400
        assert response.json()["status"] == "error"
        assert "ObjectNotFound" in response.json()["message"]

