# Generated by Django 3.1.7 on 2021-04-20 13:31

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('instance', '0005_auto_20210419_1212'),
    ]

    operations = [
        migrations.AddField(
            model_name='server',
            name='owners',
            field=models.ManyToManyField(to=settings.AUTH_USER_MODEL),
        ),
    ]
