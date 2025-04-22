from django.core.management.base import BaseCommand
from datetime import datetime, timedelta
import random
from attendance_management.models import Track, Schedule, Session, Student, AttendanceRecord

class Command(BaseCommand):
    help = 'Generate test data for schedules, sessions, and attendance records'

    def handle(self, *args, **kwargs):
        # Configuration
        start_date = datetime(2024, 10, 20)
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

        # Get the existing track with ID 4
        try:
            track = Track.objects.get(id=4)
        except Track.DoesNotExist:
            self.stdout.write(self.style.ERROR('Track with ID 4 not found!'))
            return

        # Get all students in this track
        students = Student.objects.filter(track=track)
        
        if not students:
            self.stdout.write(self.style.WARNING('No students found for this track!'))
        
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
                self.stdout.write(self.style.WARNING(f'Vacation day: {current_date.strftime("%A, %b %d")}'))
            else:
                # For remaining days, determine if the entire day is online or offline
                # Monday and Thursday are online days
                is_online = day_of_week in [0, 3]
                
                self.stdout.write(
                    self.style.SUCCESS(f'{"ONLINE" if is_online else "OFFLINE"} DAY: {current_date.strftime("%A, %b %d")}')
                )
                
                # Determine how many sessions to create (1-3)
                num_sessions = random.choice([1, 2, 3])
                
                # To avoid time overlaps, sample from session times and sort them
                available_slots = random.sample(session_times, num_sessions)
                available_slots.sort(key=lambda x: datetime.strptime(x[0].split("–")[0], "%H:%M"))
                
                for time_slot in available_slots:
                    start_time_str = time_slot[0].split("–")[0]
                    end_time_str = time_slot[0].split("–")[1]
                    
                    # Create start and end datetime objects
                    start_time = datetime.combine(
                        current_date.date(), 
                        datetime.strptime(start_time_str, "%H:%M").time()
                    )
                    end_time = datetime.combine(
                        current_date.date(), 
                        datetime.strptime(end_time_str, "%H:%M").time()
                    )
                    
                    # Create the session - all sessions for this day will have the same type
                    session = Session.objects.create(
                        track=track,
                        schedule=schedule,
                        title=random.choice(topics_pool),
                        instructor=random.choice(instructors),
                        start_time=start_time,
                        end_time=end_time,
                        session_type="online" if is_online else "offline"
                    )
                    
                    self.stdout.write(
                        f'  - Created session: {session.title} ({start_time_str} - {end_time_str})'
                    )
                    
                    # Create attendance records for all students in this track for this session
                    for student in students:
                        # INCREASED ATTENDANCE RATE: 
                        # For online sessions, much higher attendance rate (95%)
                        # For offline sessions, high attendance rate (90%)
                        attendance_threshold = 0.05 if is_online else 0.1
                        has_attended = random.random() > attendance_threshold
                        
                        # Generate check-in and check-out times with realistic behavior
                        check_in_time = None
                        check_out_time = None
                        status = 'absent'  # Default status
                        
                        if has_attended:
                            # Determine if student is on time or late (15% chance of being late)
                            is_late = random.random() < 0.15
                            
                            if is_late:
                                # Late by 5-20 minutes
                                late_minutes = random.randint(5, 20)
                                check_in_time = start_time + timedelta(minutes=late_minutes)
                            else:
                                # On time (0-10 minutes early)
                                early_minutes = random.randint(0, 10)
                                check_in_time = start_time - timedelta(minutes=early_minutes)
                            
                            # 90% of those who attended also checked out properly
                            has_checked_out = random.random() > 0.1
                            
                            if has_checked_out:
                                # Most people check out at the end time or slightly after/before
                                checkout_offset = random.randint(-10, 20)  # minutes
                                check_out_time = end_time + timedelta(minutes=checkout_offset)
                                
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
                                
                        AttendanceRecord.objects.create(
                            student=student,
                            schedule=schedule,
                            check_in_time=check_in_time,
                            check_out_time=check_out_time,
                            status=status
                        )
            
            current_date += timedelta(days=1)

        self.stdout.write(
            self.style.SUCCESS(f'Generated schedules, sessions, and attendance records for {(end_date - start_date).days + 1} days')
        )