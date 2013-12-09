import cStringIO
from xmlrpclib import Transport

from django.test.client import Client

class TestTransport(Transport):
    """
    Makes connections to XML-RPC server through Django test client.

    Usage: proxy = xmlrpclib.ServerProxy("http:///rpc/", transport=TestTransport())
    """

    def __init__(self, *args, **kwargs):
        self.client = Client()
        self._use_datetime = 0

    def request(self, host, handler, request_body, verbose=0):
        self.verbose = verbose
        if handler.startswith('http://'):
            handler = handler[7:]
        response = self.client.post(handler,
                                    request_body,
                                    content_type="text/xml")
        res = cStringIO.StringIO(response.content)
        res.seek(0)
        return self.parse_response(res)
