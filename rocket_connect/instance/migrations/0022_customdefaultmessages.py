# Generated by Django 3.2.13 on 2023-01-14 14:59

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('instance', '0021_server_default_messages'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomDefaultMessages',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField()),
                ('text', models.TextField()),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Created')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Updated')),
                ('server', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='custom_messages', to='instance.server')),
            ],
            options={
                'verbose_name': 'CustomMessages',
                'verbose_name_plural': 'Custom Messagess',
            },
        ),
    ]
