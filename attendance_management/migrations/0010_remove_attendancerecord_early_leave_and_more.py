# Generated by Django 5.1.7 on 2025-04-15 12:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('attendance_management', '0009_alter_branch_name'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='attendancerecord',
            name='early_leave',
        ),
        migrations.RemoveField(
            model_name='attendancerecord',
            name='excuse',
        ),
        migrations.RemoveField(
            model_name='attendancerecord',
            name='late_check_in',
        ),
    ]
