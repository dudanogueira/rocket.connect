# -*- coding: utf-8 -*-
from django.contrib import admin

from .models import Call, CallMessages


class MessagesInline(admin.StackedInline):
    model = CallMessages
    extra = 0


@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "unique_id",
        "previous_call",
        "answered",
        "hangup",
        "queue",
        "agent",
        "caller",
        "created",
        "updated",
    )
    list_filter = (
        "previous_call",
        "answered",
        "hangup",
        "created",
        "updated",
    )
    inlines = [
        MessagesInline,
    ]


@admin.register(CallMessages)
class CallMessagesAdmin(admin.ModelAdmin):
    list_display = ("id", "call", "json", "created", "updated")
    list_filter = ("call", "created", "updated")
