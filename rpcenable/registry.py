"""
Provide a Registration instance for XMLRPC views
"""

from SimpleXMLRPCServer import CGIXMLRPCRequestHandler
import inspect
import time
import xmlrpclib
import functools
import xml.etree.ElementTree as ET
import logging
import json
import sys, traceback
from decimal import Decimal


from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.core.serializers.json import DateTimeAwareJSONEncoder


from rpcenable.models import IncomingRequest, OutgoingRequest

LOG = logging.getLogger(__name__)

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
        # temporarily save the initial time in that var
        start = time.time()
        # prepare log record
        ir = IncomingRequest()
        ir.prefix = prefix
        ir.IP = request.META.get('REMOTE_ADDR')

        resp = self._marshaled_dispatch(request, ir=ir, startts=start)

        # save log record
        ir.completion_time = Decimal(str(time.time() - start)) # compatibility with 2.6, where Decimal can't accept float
        ir.save()
        return resp


    def handle_django_request (self,request):
        """
        Passes the request body to the CGIXMLRPCRequestHandler dispatcher
        """
        response = self._marshaled_dispatch(request)
        return response

    def system_methodSignature(self, method_name):
        """Must be overridden to provide signatures"""
        if method_name in self.funcs:
            return str(inspect.getargspec (self.funcs[method_name]))


    def _marshaled_dispatch(self, request, dispatch_method = None, path = None, ir = None, startts=None):
        """Dispatches an XML-RPC method from marshalled (XML) data.

        XML-RPC methods are dispatched from the marshalled (XML) data
        using the _dispatch method and the result is returned as
        marshalled data. For backwards compatibility, a dispatch
        function can be provided as an argument (see comment in
        SimpleXMLRPCRequestHandler.do_POST) but overriding the
        existing method through subclassing is the preferred means
        of changing method dispatch behavior.

        Copy of the original function with additional logging
        and use of Django's request/resposnses
        """

        if not request.method=='POST':
            return HttpResponse ('This method is only available via POST.', status = 400)

        # Django changed the location of the request contents at some point
        data = getattr(request,'body',None) or (request,'raw_post_data')

        try:
            params, method = xmlrpclib.loads(data)
            if ir:
                # record the params/method here, in order to avoid multiple calls to loads
                ir.params, ir.method = params, method

            # generate response
            if dispatch_method is not None:
                response = dispatch_method(method, params)
            else:
                response = self._dispatch(method, params)
            # wrap response in a singleton tuple
            response = (response,)
            response = xmlrpclib.dumps(response, methodresponse=1,
                                       allow_none=self.allow_none, encoding=self.encoding)
        except xmlrpclib.Fault, fault:
            response = xmlrpclib.dumps(fault, allow_none=self.allow_none,
                                       encoding=self.encoding)
        except Exception, e:
            # report exception back to server
            exc_type, exc_value, exc_tb = sys.exc_info()
            if ir:
                LOG.exception (u'Exception in incoming XMLRPC call: %s' % e)
                if startts:
                    ir.completion_time = Decimal(str(time.time() - startts))
                else:
                    ir.completion_time = 0
                lines = traceback.format_exception(exc_type, exc_value, exc_tb)
                ir.exception = ''.join(lines)
                ir.save()
            response = xmlrpclib.dumps(
                xmlrpclib.Fault(1, "%s:%s" % (exc_type, exc_value)),
                encoding=self.encoding, allow_none=self.allow_none,
                )

        return HttpResponse(response, mimetype='text/xml')


class RPCRegistry (object):
    """
    Central registry that keeps track of/exposes all rpc-enabled functions
    """
    def __init__ (self,  logging, allow_none, encoding):
        self.allow_none = allow_none
        self.encoding = encoding
        self.reg = {'': CustomCGIXMLRPCRequestHandler(allow_none=allow_none, encoding=encoding)}
        self.reg[''].register_introspection_functions()
        self.logging = logging

    def _add_function (self, function, prefix):
        r = self.reg.get(prefix)
        if not r:
            # create the prefix on the fly
            self.reg[prefix] = CustomCGIXMLRPCRequestHandler(allow_none=self.allow_none, encoding=self.encoding)
            self.reg[prefix].register_introspection_functions()
        # register the decorated function, and return it with no changes
        self.reg[prefix].register_function (function)

    def register_rpc (self, *exargs, **exkw):
        """
        Decorator with optional arguments, that register a function as an RPC call
        """

        prefix = exkw.get('prefix','')

        def outer (f):
            self._add_function (f, prefix, name=name)
            return f

        if len (exargs) == 1 and len(exkw) == 0 and (inspect.isfunction(args[0])):
            # In this case we only got 1 argument, and it is the decorated function
            return outer(exargs[0])
        else:
            return outer

    @csrf_exempt
    def view (self, request, prefix=''):
        if not prefix in self.reg:
            return HttpResponse ('Unknown XMLRPC prefix', status = 400)
        if self.logging:
            return self.reg[prefix].log_handle_django_request(request, prefix)
        return self.reg[prefix].handle_django_request(request)

# Instantiate the registry
rpcregistry = RPCRegistry(logging = getattr(settings, 'RPCENABLE_LOG_INCOMING',False),
                          allow_none= getattr(settings, 'RPCENABLE_ALLOW_NONE',True),
                          encoding = getattr(settings, 'RPCENABLE_ENCODING',None),
                          )

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
        outr = OutgoingRequest (method = methodname,
                                params = self._prepare_data_for_log(mod_params),
                                url = url)
        start = time.time()
        try:
            result = xmlrpclib.ServerProxy._ServerProxy__request(self, methodname, mod_params)
        except Exception, e:
            LOG.exception (u'Exception in external XMLRPC call: %s' % e)
            lines = traceback.format_exception(*sys.exc_info())
            outr.exception = ''.join(lines)
            outr.completion_time = Decimal(str(time.time() - start)) # compatibility with 2.6, where Decimal can't accept float
            outr.save()
            raise
        outr.response = self._prepare_data_for_log(result)
        outr.completion_time = Decimal(str(time.time() - start)) # compatibility with 2.6, where Decimal can't accept float
        outr.save()
        return result

    def __getattr__(self, name):
        if not name.startswith('__'):
            # magic method dispatcher
            return xmlrpclib._Method(self.__request, name)
        raise AttributeError("Attribute %r not found" % (name,))


    def _prepare_data_for_log(self, data):
        try:
            result = json.dumps(data, ensure_ascii=False, cls=DateTimeAwareJSONEncoder)
        except:
            L = logging.getLogger(name='rpcenable')
            L.warning("Unable to JSON encode data for logging. Falling back to repr.",
                      exc_info=True)
            result = repr(data)

        return result


