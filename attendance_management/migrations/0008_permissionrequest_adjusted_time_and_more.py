# Generated by Django 5.1.7 on 2025-04-13 04:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance_management', '0007_alter_schedule_created_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='permissionrequest',
            name='adjusted_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='schedule',
            name='created_at',
            field=models.DateField(db_index=True),
        ),
        migrations.AddIndex(
            model_name='attendancerecord',
            index=models.Index(fields=['check_in_time'], name='attendance__check_i_3d05c0_idx'),
        ),
        migrations.AddIndex(
            model_name='attendancerecord',
            index=models.Index(fields=['check_out_time'], name='attendance__check_o_bee049_idx'),
        ),
        migrations.AddIndex(
            model_name='attendancerecord',
            index=models.Index(fields=['student'], name='attendance__student_a8d3ce_idx'),
        ),
        migrations.AddIndex(
            model_name='attendancerecord',
            index=models.Index(fields=['schedule'], name='attendance__schedul_09ccde_idx'),
        ),
    ]
