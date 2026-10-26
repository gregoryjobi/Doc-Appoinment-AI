from django.contrib import admin
from .models import Department, PatientProfile, DoctorProfile, DoctorSchedule, Appointment, FAQ

admin.site.register(Department)
admin.site.register(PatientProfile)
admin.site.register(DoctorProfile)
admin.site.register(DoctorSchedule)
admin.site.register(Appointment)
admin.site.register(FAQ)