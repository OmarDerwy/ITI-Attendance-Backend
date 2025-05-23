# Generated by Django 5.1.7 on 2025-04-04 20:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance_management', '0003_track_program_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='schedule',
            name='is_shared',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='session',
            name='instructor',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
