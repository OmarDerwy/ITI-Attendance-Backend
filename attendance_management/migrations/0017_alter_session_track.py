# Generated by Django 5.2 on 2025-05-11 10:15

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance_management', '0016_alter_branch_branch_manager'),
    ]

    operations = [
        migrations.AlterField(
            model_name='session',
            name='track',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='attendance_management.track'),
        ),
    ]
