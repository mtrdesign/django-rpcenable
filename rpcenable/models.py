from django.db import models

from django.conf import settings
from django.utils.importlib import import_module

import xmlrpclib

pkgname, modname = getattr(settings,'RPCENABLE_USER_MODEL','rpcenable.abstractmodels.SampleUser').rsplit('.',1)
APIUser = getattr(import_module (pkgname), modname)
ADMIN_USER_ENABLE = pkgname == 'rpcenable.abstractmodels'

class IncomingRequest (models.Model):
    """
    Log for incoming XMLRPC requests.
    """
    method = models.CharField ('Name', max_length=255)
    params = models.CharField ('Params', max_length=255)
    prefix = models.CharField ('Prefix', max_length=255, blank=True, default='')
    IP = models.IPAddressField ('IP Address', null = True, blank = True)
    completion_time = models.DecimalField ('Duration', max_digits=5, decimal_places=2)
    exception = models.TextField (blank=True, null = True)
    created = models.DateTimeField('Created at', auto_now = True)
    updated = models.DateTimeField('Modified at', auto_now_add = True)

    def __unicode__ (self):
        return self.method

    class Meta:
        verbose_name = 'Inbound Request Log'


class OutgoingRequest (models.Model):
    """
    Send and log for outgoing XMLRPC requests.
    """
    url = models.URLField('URL')
    method = models.CharField ('Name', max_length=255)
    params = models.CharField ('Params', max_length=255)
    completion_time = models.DecimalField ('Duration', max_digits=5, decimal_places=2)
    exception = models.TextField (blank=True, null = True)
    created = models.DateTimeField('Created at', auto_now = True)
    updated = models.DateTimeField('Modified at', auto_now_add = True)

    class Meta:
        verbose_name = 'Outbound Request Log'
