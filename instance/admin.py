# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import Server, Connector


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'enabled',
        'url',
        'admin_user',
        'admin_password',
        'bot_user',
        'bot_password',
        'managers',
        'created',
        'updated',
    )
    list_filter = ('enabled', 'created', 'updated')
    search_fields = ('name',)


@admin.register(Connector)
class ConnectorAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'token', 'server', 'connector_type')
    list_filter = ('server', 'created', 'updated')
