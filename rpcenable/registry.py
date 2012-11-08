"""
Provide a Registration instance for XMLRPC views
"""

from SimpleXMLRPCServer import CGIXMLRPCRequestHandler
import inspect
import time
import xmlrpclib
import functools
import xml.etree.ElementTree as ET

from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from rpcenable.models import IncomingRequest, OutgoingRequest

class CustomCGIXMLRPCRequestHandler (CGIXMLRPCRequestHandler):
    """
    Override the default CGIXMLRPCRequestHandler in order to enable it to read form
    Django request instances.
    """

    def log_handle_django_request (self,request, prefix = ''):
        """
        This method handles the incoming RPC request and logs the corresponding information
        as a new IncomingRequest instance. It will add processing overhead so it might be
        unsuitable when going for max performance.
        """
        tstart = time.time()
        ir = IncomingRequest()
        # Django changed the location of the request contents at some point
        ir.params, ir.method = xmlrpclib.loads(getattr(request,'body',None) or (request,'raw_post_data'))
        ir.prefix = prefix
        ir.IP = request.META.get('REMOTE_ADDR')
        try:
            resp = self.handle_django_request(request)
        except Exception, e:
            ir.exception = e
            ir.completion_time = time.time() - tstart
            ir.save()
            raise

        if '<name>faultString</name>' in resp.content:
            ir.exception = ET.fromstring (resp.content).find(".//string").text or resp.content
        ir.completion_time = time.time() - tstart
        ir.save()
        return resp


    def handle_django_request (self,request):
        """
        Passes the request body to the CGIXMLRPCRequestHandler dispatcher
        """
        if not request.method=='POST':
            return HttpResponse ('This method is only available via POST.', status = 400)
        r_text = self._marshaled_dispatch(getattr(request,'body',None) or (request,'raw_post_data'))
        return HttpResponse(r_text, mimetype='text/xml')

    def system_methodSignature(self, method_name):
        """Must be overridden to provide signatures"""
        if method_name in self.funcs:
            return str(inspect.getargspec (self.funcs[method_name]))

class RCPRegistry (object):
    """
    Central registry that keeps track of/exposes all rpc-enabled functions
    """
    def __init__ (self,  logging = True):
        self.reg = {'': CustomCGIXMLRPCRequestHandler()}
        self.reg[''].register_introspection_functions()
        self.logging = logging


    def register_rpc (self, f, prefix = ''):
        # create the prefix on the fly
        r = self.reg.get(prefix)
        if not r:
            self.reg[prefix] = CustomCGIXMLRPCRequestHandler()
            self.reg[prefix].register_introspection_functions()
        # register the decorated function, and return it with no changes
        self.reg[prefix].register_function (f)
        @functools.wraps(f)
        def wrapper (*args, **kwargs):
            return f(*args, **kwds)
        return wrapper

    @csrf_exempt
    def view (self, request, prefix=''):
        if not prefix in self.reg:
            return HttpResponse ('Unknown XMLRPC prefix', status = 400)
        if self.logging:
            return self.reg[prefix].log_handle_django_request(request, prefix)
        return self.reg[prefix].handle_django_request(request)

# Instantiate the registry
rpcregistry = RCPRegistry(logging = getattr(settings, 'RPCENABLE_LOG_INCOMING',False))

class XMLRPCPoint (xmlrpclib.ServerProxy):
    """
    Thin wrapper over the xmlrpclib.ServerProxy class to allow logged calls
    to XMLRPC servers.
    The constructor takes an optional param_hook keyword argument, whichis
    supposed to be a lamdda function taking call params as a first argument
    and returning a modified params list.
    """
    def __init__ (self, *args, **kwargs):
        self.__param_hook = kwargs.pop('param_hook',lambda x:x)
        return xmlrpclib.ServerProxy.__init__(self, *args, **kwargs)

    def __request(self, methodname, params):
        mod_params = self.__param_hook(params)
        if not getattr(settings, 'RPCENABLE_LOG_OUTGOING',False):
            return xmlrpclib.ServerProxy._ServerProxy__request(self, methodname, mod_params)
        url = getattr(self, '_ServerProxy__host','Unknown') + getattr(self, '_ServerProxy__handler','')
        outr = OutgoingRequest (method = methodname, params = mod_params, url = url)
        start = time.time()
        try:
            result = xmlrpclib.ServerProxy._ServerProxy__request(self, methodname, mod_params)
        except Exception, e:
            outr.exception = str(e)
            outr.completion_time = time.time()- start
            outr.save()
            raise
        outr.response = result
        outr.completion_time = time.time()- start
        outr.save()
        return result

    def __getattr__(self, name):
        if not name.startswith('__'):
            # magic method dispatcher
            return xmlrpclib._Method(self.__request, name)
        raise AttributeError("Attribute %r not found" % (name,))


