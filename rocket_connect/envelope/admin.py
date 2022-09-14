from django.contrib import admin

from .models import LiveChatRoom, Message


@admin.register(LiveChatRoom)
class LiveChatRoomAdmin(admin.ModelAdmin):
    list_display = ("room_id", "connector", "open", "token", "created", "updated")
    list_filter = (
        "open",
        "connector",
        "created",
        "updated",
    )
    date_hierarchy = "created"
    ordering = ("-created",)
    search_fields = "room_id", "token"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    search_fields = ("envelope_id", "room__room_id", "room__token")
    list_display = (
        "id",
        "envelope_id",
        "type",
        "delivered",
        "get_room_id",
        "connector",
        "created",
    )
    list_filter = ("connector", "delivered", "type", "created", "updated")
    ordering = ("-created",)
    date_hierarchy = "created"

    @admin.display(ordering="rom__rom_id", description="RC Room")
    def get_room_id(self, obj):
        if obj.room:
            return obj.room.room_id
        return None
