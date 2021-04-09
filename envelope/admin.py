# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import LiveChatRoom, Message


@admin.register(LiveChatRoom)
class LiveChatRoomAdmin(admin.ModelAdmin):
    list_display = ('room_id', 'connector', 'open','token', 'created', 'updated')
    list_filter = ('open', 'connector', 'created', 'updated', )
    date_hierarchy = 'created'
    ordering = '-created',


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'room',
        'type',
        'delivered',
        'connector',
        'created'
    )
    list_filter = ('connector', 'delivered', 'created', 'updated')
    ordering = '-created',
    date_hierarchy = 'created'