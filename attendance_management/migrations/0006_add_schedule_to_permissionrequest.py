from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('attendance_management', '0005_create_permission_request_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionrequest',
            name='schedule',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='permission_requests',
                to='attendance_management.schedule',
                null=True,
                blank=True
            ),
        ),
    ]
