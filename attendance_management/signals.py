import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Schedule, Student, Session, Event, Guest
from lost_and_found_system.utils import send_and_save_notification

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Session)
def notify_students_on_session_create_or_update(sender, instance, created, **kwargs):
    """
    Signal handler to notify students when a session is created or updated
    """
    action = None  # Initialize to avoid unbound variable error
    try:
        # Get the schedule for this session
        schedule = instance.schedule
        
        # Determine if this is a regular session (track-based) or event sub-session
        if schedule.track:
            # Regular track session - notify students in the track
            track = schedule.track
            students = Student.objects.filter(track=track, user__is_active=True, track__is_active=True)
            context_info = f"for {track.name}"
            notification_context = f"track {track.name}"
        elif schedule.event:
            # Event sub-session - notify based on event's audience_type and target_tracks
            event = schedule.event
            students = []
            
            if event.audience_type in ['students_only', 'both']:
                if event.target_tracks.exists():
                    # Notify students in specific target tracks
                    students = Student.objects.filter(
                        track__in=event.target_tracks.all(),
                        user__is_active=True,
                        track__is_active=True
                    )
                    track_names = ", ".join([track.name for track in event.target_tracks.all()])
                    context_info = f"for tracks: {track_names}"
                    notification_context = f"event targeting {track_names}"
                else:
                    # Notify all active students if no target tracks specified
                    students = Student.objects.filter(
                        user__is_active=True,
                        track__is_active=True
                    )
                    context_info = "for all students"
                    notification_context = "event for all students"
            else:
                # Event is guests_only - no students to notify
                students = []
                context_info = "for guests only"
                notification_context = "guest-only event"
        else:
            # Schedule has neither track nor event - log warning and skip
            logger.warning(f"Schedule {schedule.id} has neither track nor event. Skipping session notifications.")
            return

        if created:
            # Session was created
            title = "New Session Created"
            message = (
                f"New session '{instance.title}' has been added to schedule "
                f"'{schedule.name}' {context_info} on {schedule.created_at.strftime('%d %b, %Y')}"
            )
            action = "creation"
        else:
            # Session was updated
            title = "Session Updated"
            message = (
                f"Session '{instance.title}' {context_info} on "
                f"{schedule.created_at.strftime('%d %b, %Y')} has been updated"
            )
            action = "update"

        logger.info(
            f"Preparing to send session {action} notifications to {len(students)} students for {notification_context}"
        )

        # Send notification to each student
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
                    logger.info(
                        f"Successfully sent session {action} notification {notification.id} to {student.user.email}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error sending session {action} notification to {student.user.email}: {str(e)}",
                        exc_info=True
                    )

        logger.info(
            f"Successfully sent {notification_count} session {action} notifications out of {len(students)} students"
        )

    except Exception as e:
        logger.error(
            f"Unexpected error in session {'notification' if action is None else action + ' notification'} handler: {str(e)}",
            exc_info=True
        )


@receiver(post_delete, sender=Session)
def notify_students_on_session_deletion(sender, instance, **kwargs):
    """
    Signal handler to notify students when a session is deleted
    """
    try:
        # Get the schedule for this session
        schedule = instance.schedule
        
        # Determine if this is a regular session (track-based) or event sub-session
        if schedule.track:
            # Regular track session - notify students in the track
            track = schedule.track
            students = Student.objects.filter(track=track, user__is_active=True, track__is_active=True)
            context_info = f"for {track.name}"
            notification_context = f"track {track.name}"
        else:
            # Check if this schedule has an event (safely handle case where event might be deleted)
            try:
                event = schedule.event
                if event:
                    # Event sub-session - notify based on event's audience_type and target_tracks
                    students = []
                    
                    if event.audience_type in ['students_only', 'both']:
                        if event.target_tracks.exists():
                            # Notify students in specific target tracks
                            students = Student.objects.filter(
                                track__in=event.target_tracks.all(),
                                user__is_active=True,
                                track__is_active=True
                            )
                            track_names = ", ".join([track.name for track in event.target_tracks.all()])
                            context_info = f"for tracks: {track_names}"
                            notification_context = f"event targeting {track_names}"
                        else:
                            # Notify all active students if no target tracks specified
                            students = Student.objects.filter(
                                user__is_active=True,
                                track__is_active=True
                            )
                            context_info = "for all students"
                            notification_context = "event for all students"
                    else:
                        # Event is guests_only - no students to notify
                        students = []
                        context_info = "for guests only"
                        notification_context = "guest-only event"
                else:
                    # Schedule has no associated event or track - skip
                    logger.warning(f"Schedule {schedule.id} has no associated event or track. Skipping session notifications.")
                    return
            except Event.DoesNotExist:
                # Event was deleted (CASCADE) - skip notifications since event is gone
                logger.info(f"Event associated with schedule {schedule.id} was deleted. Skipping session deletion notifications.")
                return

        title = "Session Deleted"
        message = (
            f"Session '{instance.title}' has been removed from schedule "
            f"'{schedule.name}' {context_info} on {schedule.created_at.strftime('%d %b, %Y')}"
        )

        logger.info(
            f"Sending session deletion notifications to {len(students)} students for {notification_context}"
        )        # Send notification to each student
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
                    logger.info(
                        f"Successfully sent session deletion notification to {student.user.email}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error sending session deletion notification to {student.user.email}: {str(e)}",
                        exc_info=True
                    )

        logger.info(
            f"Successfully sent {notification_count} session deletion notifications out of {len(students)} students"
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in session deletion notification handler: {str(e)}",
            exc_info=True
        )


@receiver(post_save, sender=Event)
def notify_users_on_event_create_or_update(sender, instance, created, **kwargs):
    """
    Signal handler to notify users when an event is created or updated
    """
    action = None
    try:
        event = instance
        
        # Determine action
        if created:
            title = "New Event Created"
            action = "creation"
        else:
            title = "Event Updated"
            action = "update"

        # Get event details for message
        try:
            schedule = event.schedule
            event_name = schedule.name
            event_date = schedule.created_at.strftime('%d %b, %Y')
            branch_name = schedule.custom_branch.name
        except:
            # Fallback if schedule doesn't exist yet
            event_name = "New Event"
            event_date = "TBD"
            branch_name = "TBD"

        # Determine who to notify based on audience type
        students_to_notify = []
        guests_to_notify = []

        if event.audience_type in ['students_only', 'both']:
            if event.target_tracks.exists():
                # Notify students in specific target tracks
                students_to_notify = Student.objects.filter(
                    track__in=event.target_tracks.all(),
                    user__is_active=True,
                    track__is_active=True
                )
                track_names = ", ".join([track.name for track in event.target_tracks.all()])
                audience_info = f"for tracks: {track_names}"
            else:
                # Notify all active students if no target tracks specified
                students_to_notify = Student.objects.filter(
                    user__is_active=True,
                    track__is_active=True
                )
                audience_info = "for all students"

        if event.audience_type in ['guests_only', 'both']:
            # Notify all active guests
            guests_to_notify = Guest.objects.filter(user__is_active=True)
            if event.audience_type == 'guests_only':
                audience_info = "for guests only"
            elif event.audience_type == 'both':
                audience_info = audience_info + " and guests" if 'audience_info' in locals() else "for guests"

        # Create message
        message = (
            f"Event '{event_name}' scheduled for {event_date} at {branch_name} branch "
            f"has been {'created' if created else 'updated'}. {audience_info}"
        )

        total_users = len(students_to_notify) + len(guests_to_notify)
        logger.info(
            f"Preparing to send event {action} notifications to {len(students_to_notify)} students "
            f"and {len(guests_to_notify)} guests (total: {total_users}) for event '{event_name}'"
        )

        # Send notifications to students
        notification_count = 0
        for student in students_to_notify:
            if student.user:
                try:
                    notification = send_and_save_notification(
                        user=student.user,
                        title=title,
                        message=message
                    )
                    notification_count += 1
                    logger.info(
                        f"Successfully sent event {action} notification {notification.id} to student {student.user.email}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error sending event {action} notification to student {student.user.email}: {str(e)}",
                        exc_info=True
                    )

        # Send notifications to guests
        for guest in guests_to_notify:
            if guest.user:
                try:
                    notification = send_and_save_notification(
                        user=guest.user,
                        title=title,
                        message=message
                    )
                    notification_count += 1
                    logger.info(
                        f"Successfully sent event {action} notification {notification.id} to guest {guest.user.email}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error sending event {action} notification to guest {guest.user.email}: {str(e)}",
                        exc_info=True
                    )

        logger.info(
            f"Successfully sent {notification_count} event {action} notifications out of {total_users} total users"
        )

    except Exception as e:
        logger.error(
            f"Unexpected error in event {'notification' if action is None else action + ' notification'} handler: {str(e)}",
            exc_info=True
        )


@receiver(post_delete, sender=Event)
def notify_users_on_event_deletion(sender, instance, **kwargs):
    """
    Signal handler to notify users when an event is deleted
    """
    try:
        event = instance
        
        # Get event details for message
        try:
            schedule = event.schedule
            event_name = schedule.name
            event_date = schedule.created_at.strftime('%d %b, %Y')
            branch_name = schedule.custom_branch.name
        except:
            # Fallback if schedule doesn't exist
            event_name = "Event"
            event_date = "scheduled date"
            branch_name = "branch"

        # Determine who to notify based on audience type
        students_to_notify = []
        guests_to_notify = []

        if event.audience_type in ['students_only', 'both']:
            if event.target_tracks.exists():
                # Notify students in specific target tracks
                students_to_notify = Student.objects.filter(
                    track__in=event.target_tracks.all(),
                    user__is_active=True,
                    track__is_active=True
                )
                track_names = ", ".join([track.name for track in event.target_tracks.all()])
                audience_info = f"for tracks: {track_names}"
            else:
                # Notify all active students if no target tracks specified
                students_to_notify = Student.objects.filter(
                    user__is_active=True,
                    track__is_active=True
                )
                audience_info = "for all students"

        if event.audience_type in ['guests_only', 'both']:
            # Notify all active guests
            guests_to_notify = Guest.objects.filter(user__is_active=True)
            if event.audience_type == 'guests_only':
                audience_info = "for guests only"
            elif event.audience_type == 'both':
                audience_info = audience_info + " and guests" if 'audience_info' in locals() else "for guests"

        title = "Event Cancelled"
        message = (
            f"Event '{event_name}' scheduled for {event_date} at {branch_name} branch "
            f"has been cancelled. {audience_info}"
        )

        total_users = len(students_to_notify) + len(guests_to_notify)
        logger.info(
            f"Sending event deletion notifications to {len(students_to_notify)} students "
            f"and {len(guests_to_notify)} guests (total: {total_users}) for event '{event_name}'"
        )

        # Send notifications to students
        notification_count = 0
        for student in students_to_notify:
            if student.user:
                try:
                    notification = send_and_save_notification(
                        user=student.user,
                        title=title,
                        message=message
                    )
                    notification_count += 1
                    logger.info(
                        f"Successfully sent event deletion notification to student {student.user.email}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error sending event deletion notification to student {student.user.email}: {str(e)}",
                        exc_info=True
                    )

        # Send notifications to guests
        for guest in guests_to_notify:
            if guest.user:
                try:
                    notification = send_and_save_notification(
                        user=guest.user,
                        title=title,
                        message=message
                    )
                    notification_count += 1
                    logger.info(
                        f"Successfully sent event deletion notification to guest {guest.user.email}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error sending event deletion notification to guest {guest.user.email}: {str(e)}",
                        exc_info=True
                    )

        logger.info(
            f"Successfully sent {notification_count} event deletion notifications out of {total_users} total users"
        )

    except Exception as e:
        logger.error(
            f"Unexpected error in event deletion notification handler: {str(e)}",
            exc_info=True
        )


