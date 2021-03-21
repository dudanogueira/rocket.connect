# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import LiveChatRoom, Message


@admin.register(LiveChatRoom)
class LiveChatRoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'connector', 'token', 'created', 'updated')
    list_filter = ('connector', 'created', 'updated')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'room',
        'connector',
        'created'
    )
    list_filter = ('room', 'connector', 'delivered', 'created', 'updated')
