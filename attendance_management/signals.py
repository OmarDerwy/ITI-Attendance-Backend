import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Schedule, Student, Session
from lost_and_found_system.utils import send_and_save_notification

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Session)
def notify_students_on_session_create_or_update(sender, instance, created, **kwargs):
    """
    Signal handler to notify students when a session is created or updated
    """
    try:
        # Get the schedule and track for this session
        schedule = instance.schedule
        track = schedule.track
        students = Student.objects.filter(track=track)
        
        if created:
            # Session was created
            title = "New Session Created"
            message = f"New session '{instance.title}' has been added to schedule '{schedule.name}' for {track.name} on {schedule.created_at.strftime('%d %b, %Y')}"
            action = "creation"
        else:
            # Session was updated
            title = "Session Updated"
            message = f"Session '{instance.title}' for {track.name} on {schedule.created_at.strftime('%d %b, %Y')} has been updated"
            action = "update"
        
        logger.info(f"Preparing to send session {action} notifications to {students.count()} students in {track.name}")
        
        # Send notification to each student in the track
        notification_count = 0
        for student in students:
            if student.user:  # Ensure student has a user before attempting to notify
                try:
                    notification = send_and_save_notification(
                        user=student.user,
                        title=title,
                        message=message
                    )
                    notification_count += 1
                    logger.info(f"Successfully sent session {action} notification {notification.id} to {student.user.email}")
                except Exception as e:
                    logger.error(f"Error sending session {action} notification to {student.user.email}: {str(e)}", exc_info=True)
        
        logger.info(f"Successfully sent {notification_count} session {action} notifications out of {students.count()} students")
    
    except Exception as e:
        # Catch any other exceptions to prevent signal failures
        logger.error(f"Unexpected error in session {action} notification handler: {str(e)}", exc_info=True)

@receiver(post_delete, sender=Session)
def notify_students_on_session_deletion(sender, instance, **kwargs):
    """
    Signal handler to notify students when a session is deleted
    """
    try:
        # Get the schedule and track for this session
        schedule = instance.schedule
        track = schedule.track
        students = Student.objects.filter(track=track)
        
        title = "Session Deleted"
        message = f"Session '{instance.title}' has been removed from schedule '{schedule.name}' for {track.name} on {schedule.created_at.strftime('%d %b, %Y')}"
        
        logger.info(f"Sending session deletion notifications to {students.count()} students in {track.name}")
        
        # Send notification to each student in the track
        notification_count = 0
        for student in students:
            if student.user:  # Ensure student has a user before attempting to notify
                try:
                    notification = send_and_save_notification(
                        user=student.user,
                        title=title,
                        message=message
                    )
                    notification_count += 1
                    logger.info(f"Successfully sent session deletion notification to {student.user.email}")
                except Exception as e:
                    logger.error(f"Error sending session deletion notification to {student.user.email}: {str(e)}", exc_info=True)
        
        logger.info(f"Successfully sent {notification_count} session deletion notifications out of {students.count()} students")
    except Exception as e:
        # Catch any other exceptions to prevent signal failures
        logger.error(f"Unexpected error in session deletion notification handler: {str(e)}", exc_info=True)
