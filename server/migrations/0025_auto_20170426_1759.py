# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2017-04-26 17:59
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0024_auto_20170408_0118'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='module',
            options={'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='module',
            name='category',
            field=models.CharField(default='General', max_length=200, verbose_name='category'),
            preserve_default=False,
        ),
    ]
