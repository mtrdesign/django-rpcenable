from django.contrib import admin
from rpcenable.models import IncomingRequest, OutgoingRequest, APIUser, ADMIN_USER_ENABLE
from rpcenable.abstractmodels import APIUserAdmin

class IncomingRequestAdmin(admin.ModelAdmin):
    date_hierarchy = 'created'
    list_display = ('method','params','prefix','completion_time','exception','IP','created')
    list_filter = ('method','prefix',)
    search_fields = ('method','params','exception')

class OutgoingRequestAdmin(admin.ModelAdmin):
    date_hierarchy = 'created'
    list_display = ('url','method','params','response','completion_time','exception','created')
    #list_filter = ('method','url',)
    search_fields = ('method','params','exception', 'response')

admin.site.register (IncomingRequest, IncomingRequestAdmin)
admin.site.register (OutgoingRequest, OutgoingRequestAdmin)

if ADMIN_USER_ENABLE:
    admin.site.register (APIUser, APIUserAdmin)
