# Generated by Django 3.1.7 on 2021-04-20 20:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('envelope', '0005_auto_20210412_2037'),
    ]

    operations = [
        migrations.AlterField(
            model_name='message',
            name='delivered',
            field=models.BooleanField(default=False),
        ),
    ]
