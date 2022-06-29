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
        "caller_left_queue",
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
        "caller_left_queue",
        "answered",
        "hangup",
        "created",
        "updated",
    )
    date_hierarchy = "created"
    inlines = [
        MessagesInline,
    ]


@admin.register(CallMessages)
class CallMessagesAdmin(admin.ModelAdmin):
    list_display = ("id", "call", "json", "created", "updated")
    list_filter = ("call", "created", "updated")
