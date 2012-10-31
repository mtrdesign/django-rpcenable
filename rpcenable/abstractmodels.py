from django.db import models
from django.conf import settings
from django.contrib import admin
# Create your models here.

class BaseAPIUser (models.Model):
    """
    User object used by the authentication library.
    """
    username = models.CharField ('Username', max_length=255, unique=True)
    secret = models.CharField ('Secret', max_length=255)
    active = models.BooleanField('Active',default = True)
    last_login = models.DateTimeField('Last auth', null = True, blank = True)

    def __unicode__ (self):
        return self.username

    class Meta:
        verbose_name = 'API User'
        abstract = True

class SampleUser (BaseAPIUser):
    """Importable reincarnation of the BaseAPIUser"""
    pass

class APIUserAdmin(admin.ModelAdmin):
    """Sample admin for the API User"""
    date_hierarchy = 'last_login'
    list_display = ('username', 'last_login', 'active')
    list_filter = ('active','last_login',)
    search_fields = ('username',)