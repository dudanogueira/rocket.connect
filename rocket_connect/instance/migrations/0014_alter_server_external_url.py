# Generated by Django 3.2.13 on 2022-05-18 21:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('instance', '0013_auto_20220518_1833'),
    ]

    operations = [
        migrations.AlterField(
            model_name='server',
            name='external_url',
            field=models.CharField(blank=True, help_text='This field is used to link to actual server. If blank, url is used.', max_length=150),
        ),
    ]
