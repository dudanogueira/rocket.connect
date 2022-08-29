# Generated by Django 3.2.13 on 2022-07-23 16:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_celery_beat', '0015_edit_solarschedule_events_choices'),
        ('instance', '0017_rename_server_tasks_server_tasks'),
    ]

    operations = [
        migrations.AlterField(
            model_name='server',
            name='tasks',
            field=models.ManyToManyField(blank=True, to='django_celery_beat.PeriodicTasks'),
        ),
    ]