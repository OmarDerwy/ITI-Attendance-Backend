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
        session_times = [("09:00–12:00",), ("10:00–13:00",), ("14:00–16:00",), ("16:00–18:00",)]

        # Get the existing track with ID 1
        try:
            track = Track.objects.get(id=1)
        except Track.DoesNotExist:
            self.stdout.write(self.style.ERROR('Track with ID 1 not found!'))
            return

        # Get all students in this track
        students = Student.objects.filter(track=track)
        
        if not students:
            self.stdout.write(self.style.WARNING('No students found for this track!'))
        
        # Generate Schedules and Sessions
        current_date = start_date
        while current_date <= end_date:
            # Determine day type based on the day of the week
            day_of_week = current_date.weekday()
            
            # Create a schedule for this day
            schedule = Schedule.objects.create(
                track=track,
                name=f"Schedule for {current_date.strftime('%b %d, %Y')}",
                created_at=current_date.date(),
                custom_branch=track.default_branch,
                is_shared=False
            )
            
            # Friday and Saturday are always off (weekend)
            if day_of_week in [4, 5]:  # Friday and Saturday
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
                        # For online sessions, higher attendance rate (90%)
                        # For offline sessions, normal attendance rate (80%)
                        attendance_threshold = 0.1 if is_online else 0.2
                        has_attended = random.random() > attendance_threshold
                        # 90% of those who attended also checked out properly
                        has_checked_out = has_attended and random.random() > 0.1
                        
                        AttendanceRecord.objects.create(
                            student=student,
                            schedule=schedule,
                            check_in_time=start_time if has_attended else None,
                            check_out_time=end_time if has_checked_out else None
                        )
            
            current_date += timedelta(days=1)

        self.stdout.write(
            self.style.SUCCESS(f'Generated schedules, sessions, and attendance records for {(end_date - start_date).days + 1} days')
        )