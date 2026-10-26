from django.db import models
from django.contrib.auth.models import User

# -------------------------------------------------------------
# 1. DEPARTMENTS
# -------------------------------------------------------------
class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name


# -------------------------------------------------------------
# 2. PATIENT PROFILE (Linked 1:1 with User)
# -------------------------------------------------------------
class PatientProfile(models.Model):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='patient_profile')
    phone = models.CharField(max_length=15)
    age = models.PositiveIntegerField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    blood_group = models.CharField(max_length=5, blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} (Patient)"


# -------------------------------------------------------------
# 3. DOCTOR PROFILE (Linked 1:1 with User)
# -------------------------------------------------------------
class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='doctor_profile')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='doctors')
    qualification = models.CharField(max_length=150)
    experience_years = models.PositiveIntegerField(default=0)
    consultation_fee = models.DecimalField(max_digits=10, decimal_places=2)
    room_number = models.CharField(max_length=20, blank=True, null=True)
    is_approved = models.BooleanField(default=False)  # Admin approves newly joined doctors
    clinic_name = models.CharField(max_length=150, default="Central Clinic")
    clinic_address = models.CharField(max_length=255, default="Main Street")
    latitude = models.FloatField(default=9.9816)   # Sample default latitude
    longitude = models.FloatField(default=76.2999) # Sample default longitude
    
    def __str__(self):
        return f"Dr. {self.user.get_full_name() or self.user.username} - {self.department.name}"


# -------------------------------------------------------------
# 4. DOCTOR SCHEDULE
# -------------------------------------------------------------
class DoctorSchedule(models.Model):
    DAYS_OF_WEEK = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]

    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.CharField(max_length=15, choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    slot_duration_minutes = models.PositiveIntegerField(default=30)

    def __str__(self):
        return f"{self.doctor} | {self.day_of_week} ({self.start_time} - {self.end_time})"


# -------------------------------------------------------------
# 5. APPOINTMENTS (Links Patient & Doctor + Stores AI Output)
# -------------------------------------------------------------
class Appointment(models.Model):
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name='appointments')
    doctor = models.ForeignKey(DoctorProfile, on_delete=models.CASCADE, related_name='appointments')
    appointment_date = models.DateField()
    appointment_time = models.TimeField()
    symptoms_text = models.TextField(blank=True, null=True)
    ai_predicted_dept = models.CharField(max_length=100, blank=True, null=True)
    # NEW: Stores structured clinical tags (comma-separated or JSON string)
    symptom_tags = models.CharField(max_length=255, blank=True, null=True, help_text="AI-extracted tags")
    status = models.CharField(
        max_length=20,
        choices=[
            ('Scheduled', 'Scheduled'),
            ('Completed', 'Completed'),
            ('Cancelled', 'Cancelled'),
            ('No-Show', 'No-Show')
        ],
        default='Scheduled'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def get_tags_list(self):
        """Helper to return tags as a clean Python list in templates."""
        if not self.symptom_tags:
            return []
        return [t.strip() for t in self.symptom_tags.split(',') if t.strip()]

    def __str__(self):
        return f"Apt #{self.id} - {self.patient.user.username} with Dr. {self.doctor.user.username}"


# -------------------------------------------------------------
# 6. FAQS (Used by the Guest Module lightweight chatbot)
# -------------------------------------------------------------
class FAQ(models.Model):
    question = models.TextField()
    answer = models.TextField()
    keywords = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.question[:50]

