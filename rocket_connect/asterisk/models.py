from django.db import models

# Create your models here.


class Call(models.Model):
    unique_id = models.CharField(max_length=50, unique=True)
    previous_call = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True
    )
    answered = models.DateTimeField(
        auto_now=False, auto_now_add=False, null=True, blank=True
    )
    hangup = models.DateTimeField(
        auto_now=False, auto_now_add=False, null=True, blank=True
    )
    queue = models.CharField(max_length=50, null=True, blank=True)
    agent = models.CharField(max_length=50, null=True, blank=True)
    caller = models.CharField(max_length=50, blank=True, null=True)
    caller_left_queue = models.BooleanField(default=False)
    # metadata
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(blank=True, auto_now=True, verbose_name="Updated")

    class Meta:
        verbose_name = "Call"
        verbose_name_plural = "Calls"
        ordering = ("-created",)

    def __str__(self):
        return self.unique_id


class CallMessages(models.Model):
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="messages")
    json = models.JSONField(blank=True, null=True)
    # metadata
    created = models.DateTimeField(
        blank=True, auto_now_add=True, verbose_name="Created"
    )
    updated = models.DateTimeField(blank=True, auto_now=True, verbose_name="Updated")
