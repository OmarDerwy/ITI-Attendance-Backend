from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('attendance_management', '0004_schedule_is_shared_session_instructor'),
    ]

    operations = [
        migrations.AlterField(
            model_name='schedule',
            name='track',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='Schedules', to='attendance_management.track'),
        ),
        migrations.AddConstraint(
            model_name='schedule',
            constraint=models.UniqueConstraint(fields=['created_at', 'track'], name='unique_schedule'),
        ),
    ]
