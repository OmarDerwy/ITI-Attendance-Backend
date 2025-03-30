from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('attendance_management', '0003_add_late_arrival_to_attendancerecord'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancerecord',
            name='late_check_in',
            field=models.CharField(max_length=255, blank=True, null=True),
        ),
    ]
