from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
import random
from attendance_management.models import Track, Schedule, Session, Student, AttendanceRecord
from django.db import transaction, connection
from django.utils import timezone  # Add this import

class Command(BaseCommand):
    help = 'Generate test data for schedules, sessions, and attendance records'

    def handle(self, *args, **kwargs):
        # Configuration
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 4, 30)
        instructors = ["Sarah Malik", "Usman Khan", "Bilal Shah", "Mahmoud Helmy", "Hossam El-Din", 
                      "Mohamed El-Sayed", "Omar Abdelrahman", "Yasser Mohamed", "Ali Ahmed", "Mina Nagy", 
                      "Raphael", "Marina"]
        topics_pool = [
            "HTML/CSS Basics", "JavaScript Fundamentals", "React Hooks", "Redux Intro", "React Routing",
            "Python Basics", "Flask Routing", "REST APIs", "Postman Practice", "SQL & DB Models",
            "User Auth", "Docker Basics", "CI/CD Pipelines", "Testing Flask", "Testing React",
            "Debugging & Logging", "Network Protocols", "HTTP/HTTPS", "OS File System", "Threads & Processes",
            "Capstone Planning", "Capstone Development", "Capstone Presentations", "Git Workflow", "Cloud Deployment",
            "Responsive Design with Flexbox/Grid", "JavaScript ES6+ Features", "Async JS & Fetch API",
            "React Context API", "React Performance Optimization", "Tailwind CSS Basics",
            "Animations with Framer Motion",
            "Python OOP", "Flask Blueprints", "Error Handling in Flask", "FastAPI Basics",
            "Database Migrations with Alembic", "Background Tasks with Celery",
            "PostgreSQL Joins & Indexes", "MongoDB Basics", "Query Optimization", "ORM vs Raw SQL",
            "TCP vs UDP", "Ping, Traceroute, and Netstat", "Process Management in Linux",
            "System Monitoring Tools (htop, top)", "File Permissions & Users", "Sockets Programming Intro",
            "Firewalls & Port Scanning",
            "Unit Testing with pytest", "Testing React with Jest", "API Testing with Postman/Newman",
            "Integration Testing Overview",
            "Git Rebase vs Merge", "Branching Strategy in Teams", "Docker Compose", "Intro to Kubernetes",
            "GitHub Actions for CI/CD", "VS Code Power User Tips", "Using Postman for Mock Servers",
            "Code Splitting in React", "Environment Variables & Secrets", "Deploying to Heroku",
            "NGINX Basics for Devs", "Writing Clean Code & Linters", "Logging Strategies in Prod",
            "Writing Good Technical Docs", "Time Estimation for Tasks", "Agile & Scrum Basics",
            "How to Read Technical Specs"
        ]
        session_times = [("09:00–12:00",), ("12:00–15:00",), ("16:00–18:00",)]

        # Get all available tracks
        tracks = Track.objects.all()
        
        if not tracks:
            self.stdout.write(self.style.ERROR('No tracks found!'))
            return
            
        self.stdout.write(self.style.SUCCESS(f'Found {tracks.count()} tracks. Generating data for each track...'))
        
        # Get current date for comparison
        today = timezone.now().date()  # Use timezone-aware current date
        
        # Loop through each track with transaction for better performance
        for track in tracks:
            with transaction.atomic():
                self.stdout.write(self.style.SUCCESS(f'Processing Track: {track.name} (ID: {track.id})'))
                
                # Get all ACTIVE students in this track - prefetch related user objects
                students = list(Student.objects.filter(track=track, user__is_active=True).select_related('user'))
                
                if not students:
                    self.stdout.write(self.style.WARNING(f'No active students found for track {track.name}! Skipping...'))
                    continue
                
                self.stdout.write(self.style.SUCCESS(f'Found {len(students)} active students in track {track.name}'))
                
                # Prepare to batch create attendance records
                all_attendance_records = []
                batch_size = 1000  # Set a reasonable batch size
                
                # Generate Schedules and Sessions
                current_date = start_date
                
                # Track vacation days for each week
                current_week_start = current_date - timedelta(days=current_date.weekday())
                vacation_days_of_week = random.sample(range(7), 2)  # Pick 2 random days (0=Monday, 6=Sunday)
                
                while current_date <= end_date:
                    # Check if we're in a new week, and if so, select new random vacation days
                    week_start = current_date - timedelta(days=current_date.weekday())
                    if week_start != current_week_start:
                        current_week_start = week_start
                        vacation_days_of_week = random.sample(range(7), 2)  # New random vacation days
                        self.stdout.write(self.style.SUCCESS(f'NEW WEEK: Vacation days set to {[["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day] for day in vacation_days_of_week]}'))
                    
                    # Determine day type based on whether it's a vacation day
                    day_of_week = current_date.weekday()
                    is_vacation = day_of_week in vacation_days_of_week
                    
                    # Create sessions in bulk for better performance
                    sessions_to_create = []
                    
                    # Create a schedule for this day
                    schedule = Schedule.objects.create(
                        track=track,
                        name=f"Schedule for {current_date.strftime('%b %d, %Y')}",
                        created_at=current_date.date(),
                        custom_branch=track.default_branch,
                        is_shared=False
                    )
                    
                    # Handle vacation days
                    if is_vacation:
                        self.stdout.write(self.style.WARNING(f'Vacation day for {track.name}: {current_date.strftime("%A, %b %d")}'))
                    else:
                        # For remaining days, determine if the entire day is online or offline
                        # Monday and Thursday are online days
                        is_online = day_of_week in [0, 3]
                        
                        self.stdout.write(
                            self.style.SUCCESS(f'Track {track.name}: {"ONLINE" if is_online else "OFFLINE"} DAY: {current_date.strftime("%A, %b %d")}')
                        )
                        
                        # Determine how many sessions to create (1-3)
                        num_sessions = random.choice([1, 2, 3])
                        
                        # To avoid time overlaps, sample from session times and sort them
                        available_slots = random.sample(session_times, num_sessions)
                        available_slots.sort(key=lambda x: datetime.strptime(x[0].split("–")[0], "%H:%M"))
                        
                        # Track the first session start time and last session end time
                        first_session_start_time = None
                        last_session_end_time = None
                        
                        for time_slot in available_slots:
                            start_time_str = time_slot[0].split("–")[0]
                            end_time_str = time_slot[0].split("–")[1]
                            
                            # Create timezone-aware start and end datetime objects
                            naive_start_time = datetime.combine(
                                current_date.date(), 
                                datetime.strptime(start_time_str, "%H:%M").time()
                            )
                            naive_end_time = datetime.combine(
                                current_date.date(), 
                                datetime.strptime(end_time_str, "%H:%M").time()
                            )
                            
                            # Make datetime objects timezone-aware
                            start_time = timezone.make_aware(naive_start_time)
                            end_time = timezone.make_aware(naive_end_time)
                            
                            # Update first and last session times
                            if first_session_start_time is None or start_time < first_session_start_time:
                                first_session_start_time = start_time
                            if last_session_end_time is None or end_time > last_session_end_time:
                                last_session_end_time = end_time
                            
                            # Append session to bulk create list
                            sessions_to_create.append(
                                Session(
                                    track=track,
                                    schedule=schedule,
                                    title=random.choice(topics_pool),
                                    instructor=random.choice(instructors),
                                    start_time=start_time,
                                    end_time=end_time,
                                    session_type="online" if is_online else "offline"
                                )
                            )
                        
                        # Bulk create all sessions for this day
                        Session.objects.bulk_create(sessions_to_create)
                        
                        # Now create attendance records for all students
                        for student in students:
                            attendance_record = None
                            if current_date.date() > today:
                                # For future dates, set status to pending
                                attendance_record = AttendanceRecord(
                                    student=student,
                                    schedule=schedule,
                                    check_in_time=None,
                                    check_out_time=None,
                                    status='pending'
                                )
                            else:
                                # For past dates, calculate attendance
                                attendance_threshold = 0.05 if is_online else 0.1
                                has_attended = random.random() > attendance_threshold
                                
                                # Generate check-in and check-out times with realistic behavior
                                check_in_time = None
                                check_out_time = None
                                status = 'absent'  # Default status
                                
                                if has_attended and first_session_start_time and last_session_end_time:
                                    # Determine if student is on time or late (15% chance of being late)
                                    is_late = random.random() < 0.15
                                    
                                    if is_late:
                                        # Late by 5-20 minutes
                                        late_minutes = random.randint(5, 20)
                                        check_in_time = first_session_start_time + timedelta(minutes=late_minutes)
                                    else:
                                        # On time (0-10 minutes early)
                                        early_minutes = random.randint(0, 10)
                                        check_in_time = first_session_start_time - timedelta(minutes=early_minutes)
                                    
                                    # 90% of those who attended also checked out properly
                                    has_checked_out = random.random() > 0.1
                                    
                                    if has_checked_out:
                                        # Most people check out at the end time or slightly after/before
                                        checkout_offset = random.randint(-10, 20)  # minutes
                                        check_out_time = last_session_end_time + timedelta(minutes=checkout_offset)
                                        
                                        # Set appropriate status based on check-in and check-out
                                        if is_late:
                                            status = 'late'
                                        else:
                                            status = 'attended'
                                    else:
                                        # No check-out
                                        if is_late:
                                            status = 'late-check-in_no-check-out'
                                        else:
                                            status = 'no-check-out'
                                else:
                                    # Small chance of having an excused absence
                                    is_excused = random.random() < 0.3
                                    status = 'excused' if is_excused else 'absent'
                                        
                                attendance_record = AttendanceRecord(
                                    student=student,
                                    schedule=schedule,
                                    check_in_time=check_in_time,
                                    check_out_time=check_out_time,
                                    status=status
                                )
                                
                            all_attendance_records.append(attendance_record)
                            
                            # If we've reached the batch size, bulk insert and clear the list
                            if len(all_attendance_records) >= batch_size:
                                AttendanceRecord.objects.bulk_create(all_attendance_records)
                                all_attendance_records = []
                    
                    current_date += timedelta(days=1)
                
                # Insert any remaining attendance records
                if all_attendance_records:
                    AttendanceRecord.objects.bulk_create(all_attendance_records)
                
            # End of transaction block
            
            self.stdout.write(
                self.style.SUCCESS(f'Generated schedules, sessions, and attendance records for track {track.name} for {(end_date - start_date).days + 1} days')
            )

        self.stdout.write(
            self.style.SUCCESS(f'Completed generating data for all {tracks.count()} tracks')
        )