from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('attendance_management', '0004_add_late_check_in_excuse'),
    ]

    operations = [
        migrations.CreateModel(
            name='PermissionRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_type', models.CharField(choices=[('early_leave', 'Early Leave'), ('late_check_in', 'Late Check-In'), ('day_excuse', 'Day Excuse')], max_length=20)),
                ('reason', models.TextField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='permission_requests', to='attendance_management.student')),
            ],
        ),
    ]
