# -*- coding: utf-8 -*-
# Generated by Django 1.11.17 on 2019-01-02 17:15
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0031_module_version_js_module'),
    ]

    operations = [
        migrations.AlterField(
            model_name='moduleversion',
            name='js_module',
            field=models.TextField(default='', verbose_name='js_module'),
        ),
    ]