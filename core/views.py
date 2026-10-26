import json
import datetime
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_date, parse_time
from .models import Department, DoctorProfile, PatientProfile, Appointment
import math

def calculate_noshow_risk(appointment):
    """
    Predictive Model for Appointment No-Show Risk.
    Features:
      1. Lead Time: Difference between booking creation date and appointment date.
      2. Booking History: Historical completed vs no-show/cancellation record of the patient.
      3. Timing & Patient Profile: Age factor and weekend/weekday scheduling.
    Output:
      - risk_score: Probability percentage (0 - 100%)
      - risk_level: 'Low', 'Medium', 'High'
      - lead_days: Lead time in days
      - reasons: Explainability factors for the administrator
    """
    patient = appointment.patient
    app_date = appointment.appointment_date
    created_date = appointment.created_at.date() if appointment.created_at else datetime.date.today()
    
    # 1. Lead Time Feature (in days)
    lead_days = max(0, (app_date - created_date).days)
    
    # 2. Patient Booking History
    past_appointments = Appointment.objects.filter(
        patient=patient,
        created_at__lt=appointment.created_at if appointment.created_at else datetime.datetime.now()
    ).exclude(id=appointment.id)
    
    total_past = past_appointments.count()
    past_noshows = past_appointments.filter(status='No-Show').count()
    past_cancelled = past_appointments.filter(status='Cancelled').count()
    
    # Baseline log-odds intercept (-1.8 corresponds to ~14% baseline hospital no-show rate)
    z = -1.8
    reasons = []

    # Lead time impact: +0.07 per day lead time (plateaus at 30 days)
    effective_lead = min(lead_days, 30)
    z += 0.08 * effective_lead
    if lead_days >= 7:
        reasons.append(f"Long lead time ({lead_days} days in advance)")
    elif lead_days <= 1:
        reasons.append("Short lead time (same/next day booking)")

    # Historical no-show penalty
    if past_noshows > 0:
        z += 1.4 * past_noshows
        reasons.append(f"{past_noshows} prior no-show record(s)")
    if past_cancelled > 0:
        z += 0.5 * past_cancelled
        reasons.append(f"{past_cancelled} prior cancellation(s)")
    if total_past > 2 and past_noshows == 0:
        z -= 0.6
        reasons.append("Reliable attendance history")

    # Patient Age Factor (Younger cohorts correlate statistically higher with missed slots)
    if patient.age and patient.age < 25:
        z += 0.3
    elif patient.age and patient.age > 60:
        z -= 0.4

    # Calculate Probability via Sigmoid Activation: 1 / (1 + e^-z)
    prob = 1.0 / (1.0 + math.exp(-z))
    risk_percent = int(round(prob * 100))

    if risk_percent >= 60:
        risk_level = "High"
    elif risk_percent >= 35:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    return {
        'score': risk_percent,
        'level': risk_level,
        'lead_days': lead_days,
        'reasons': ", ".join(reasons) if reasons else "Standard scheduled visit"
    }

# =============================================================
# 1. PUBLIC, GUEST, AI (LLAMA 3.2:1B CHAT) & MAP VIEWS
# =============================================================

def index_view(request):
    """Public landing page displaying approved doctors and departments."""
    departments = Department.objects.all()
    doctors = DoctorProfile.objects.filter(is_approved=True)
    return render(request, 'index.html', {
        'departments': departments,
        'doctors': doctors,
    })


@csrf_exempt
def predict_department_api(request):
    """
    AI symptom classifier powered by local llama3.2:1b via Ollama /api/chat.
    Uses IPv4 (127.0.0.1) and role-based prompt structure.
    """
    if request.method == 'POST':
        user_symptoms = ""
        try:
            data = json.loads(request.body)
            user_symptoms = data.get('symptoms', '').strip()

            if not user_symptoms:
                return JsonResponse({'department': 'General Medicine'})

            dept_names = list(Department.objects.values_list('name', flat=True))
            if not dept_names:
                dept_names = ["Cardiology", "Dermatology", "Orthopedics", "Pediatrics", "General Medicine"]

            dept_list_str = ", ".join(dept_names)

            ollama_url = "http://127.0.0.1:11434/api/chat"
            payload = {
                "model": "llama3.2:1b",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"You are a medical triage assistant. Your task is to categorize patient symptoms "
                            f"into EXACTLY ONE of these departments: [{dept_list_str}].\n"
                            f"Output ONLY the exact department name as a single word or phrase. "
                            f"Do not write explanations, sentences, markdown, or punctuation."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Patient symptoms: {user_symptoms}"
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0.0,
                    "num_predict": 15
                }
            }

            response = requests.post(ollama_url, json=payload, timeout=20)
            predicted_department = "General Medicine"

            if response.status_code == 200:
                result = response.json()
                raw_answer = result.get('message', {}).get('content', '').strip()
                print(f"\n[LLAMA 3.2:1B OUTPUT]: '{raw_answer}' for symptoms: '{user_symptoms}'")

                for dept in dept_names:
                    if dept.lower() in raw_answer.lower():
                        predicted_department = dept
                        break

                if predicted_department == "General Medicine":
                    clean = raw_answer.strip().strip('.').strip('"').strip("'")
                    if clean in dept_names:
                        predicted_department = clean
                    else:
                        lower_symp = user_symptoms.lower()
                        if any(w in lower_symp for w in ['chest', 'heart', 'palpitation', 'breath']):
                            predicted_department = "Cardiology"
                        elif any(w in lower_symp for w in ['skin', 'rash', 'acne', 'itch', 'spot']):
                            predicted_department = "Dermatology"
                        elif any(w in lower_symp for w in ['bone', 'joint', 'fracture', 'knee', 'ankle']):
                            predicted_department = "Orthopedics"
                        elif any(w in lower_symp for w in ['child', 'baby', 'toddler', 'infant']):
                            predicted_department = "Pediatrics"
            else:
                print(f"[Ollama Error Code]: {response.status_code}")

        except Exception as e:
            print(f"[Ollama Exception]: {e}")
            lower_symp = user_symptoms.lower()
            if any(w in lower_symp for w in ['chest', 'heart', 'breath']):
                predicted_department = "Cardiology"
            elif any(w in lower_symp for w in ['skin', 'rash', 'itch']):
                predicted_department = "Dermatology"
            elif any(w in lower_symp for w in ['bone', 'joint', 'knee', 'fracture']):
                predicted_department = "Orthopedics"
            elif any(w in lower_symp for w in ['child', 'baby', 'infant']):
                predicted_department = "Pediatrics"
            else:
                predicted_department = "General Medicine"

        print(f"[FINAL PREDICTED DEPARTMENT]: {predicted_department}\n")
        return JsonResponse({'department': predicted_department})

    return JsonResponse({'error': 'Invalid request'}, status=400)


def get_doctors_by_department_api(request):
    """
    Returns doctors filtered by department, sorted by highest experience first,
    including their hospital/clinic affiliation.
    """
    dept_name = request.GET.get('department', '').strip()

    doctors = DoctorProfile.objects.all()
    if dept_name:
        doctors = doctors.filter(department__name__iexact=dept_name)

    doctors = doctors.order_by('-experience_years')

    data = []
    for d in doctors:
        doc_name = d.user.get_full_name() or d.user.username
        clinic = getattr(d, 'clinic_name', None) or "Smart Health City Hospital"
        data.append({
            'id': d.id,
            'name': f"Dr. {doc_name}",
            'fee': str(d.consultation_fee),
            'qualification': d.qualification or "MBBS",
            'experience': d.experience_years or 0,
            'hospital': clinic
        })
    return JsonResponse({'doctors': data})


def nearby_hospitals_api(request):
    """Returns clinic coordinates filtered by department for Google/Leaflet maps."""
    dept_name = request.GET.get('department', '').strip()

    query = DoctorProfile.objects.filter(is_approved=True)
    if dept_name:
        query = query.filter(department__name__iexact=dept_name)

    clinics_data = []
    for doc in query:
        clinics_data.append({
            'doctor_name': f"Dr. {doc.user.username}",
            'department': doc.department.name if doc.department else "General Medicine",
            'clinic_name': getattr(doc, 'clinic_name', 'City Care Hospital'),
            'address': getattr(doc, 'clinic_address', 'Medical Center'),
            'fee': str(doc.consultation_fee),
            'lat': getattr(doc, 'latitude', 9.9816),
            'lng': getattr(doc, 'longitude', 76.2999),
        })

    return JsonResponse({'clinics': clinics_data})


@login_required(login_url='/login/?role=patient')
def book_appointment_view(request):
    if request.method == 'POST':
        # ... [keep your existing parameter extraction] ...
        symptoms_text = request.POST.get('symptoms_text', '')
        
        # 1. Generate symptom tags for fast doctor review
        symptom_tags = extract_symptom_tags(symptoms_text)

        # ... [keep doctor retrieval and date parsing] ...

        Appointment.objects.create(
            patient=patient_profile,
            doctor=doctor,
            appointment_date=appointment_date,
            appointment_time=appointment_time,
            symptoms_text=symptoms_text,
            ai_predicted_dept=ai_predicted_dept or (doctor.department.name if doctor.department else ""),
            symptom_tags=symptom_tags,  # <-- Store classified tags
            status='Scheduled'
        )

        return redirect('patient_dashboard')

    return redirect('home')

# =============================================================
# 2. AUTHENTICATION & ROLE-SPECIFIC REGISTRATION VIEWS
# =============================================================

def user_login_view(request):
    """Role-aware login handler with portal redirect routing."""
    role = request.GET.get('role', request.POST.get('role', 'patient'))

    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user:
            login(request, user)
            if user.is_superuser or user.is_staff:
                return redirect('admin_dashboard')
            elif hasattr(user, 'doctor_profile'):
                return redirect('doctor_dashboard')
            elif hasattr(user, 'patient_profile'):
                return redirect('patient_dashboard')
            return redirect('patient_dashboard')
        return render(request, 'login.html', {
            'error': 'Invalid username or password.',
            'role': role
        })

    return render(request, 'login.html', {'role': role})


def user_logout_view(request):
    """Logs out user and redirects home."""
    logout(request)
    return redirect('home')


def patient_register_view(request):
    """Handles patient account registration."""
    if request.method == 'POST':
        u = request.POST.get('username')
        e = request.POST.get('email')
        p = request.POST.get('password')
        phone = request.POST.get('phone')
        age = request.POST.get('age')
        gender = request.POST.get('gender')
        blood_group = request.POST.get('blood_group')

        if User.objects.filter(username=u).exists():
            return render(request, 'register_patient.html', {'error': 'Username already taken.'})

        user = User.objects.create_user(username=u, email=e, password=p)
        PatientProfile.objects.create(
            user=user,
            phone=phone,
            age=age,
            gender=gender,
            blood_group=blood_group
        )
        login(request, user)
        return redirect('patient_dashboard')

    return render(request, 'register_patient.html')


def doctor_register_view(request):
    """Handles doctor registration application (pending admin review)."""
    departments = Department.objects.all()

    if request.method == 'POST':
        u = request.POST.get('username')
        e = request.POST.get('email')
        p = request.POST.get('password')
        department_id = request.POST.get('department')
        qualification = request.POST.get('qualification')
        experience_years = request.POST.get('experience_years')
        consultation_fee = request.POST.get('consultation_fee')
        room_number = request.POST.get('room_number')
        clinic_name = request.POST.get('clinic_name')

        if User.objects.filter(username=u).exists():
            return render(request, 'register_doctor.html', {
                'error': 'Username already taken.',
                'departments': departments
            })

        user = User.objects.create_user(username=u, email=e, password=p)
        dept = Department.objects.get(id=department_id)

        DoctorProfile.objects.create(
            user=user,
            department=dept,
            qualification=qualification,
            experience_years=experience_years,
            consultation_fee=consultation_fee,
            room_number=room_number,
            clinic_name=clinic_name.strip() if clinic_name else "Smart Health City Hospital",
            is_approved=False
        )
        login(request, user)
        return redirect('doctor_dashboard')

    return render(request, 'register_doctor.html', {'departments': departments})


# =============================================================
# 3. PATIENT PORTAL VIEWS (USER SPECIFIC)
# =============================================================

@login_required(login_url='/login/?role=patient')
def patient_dashboard_view(request):
    """Patient dashboard displaying solely the logged-in user's appointments."""
    patient_profile, _ = PatientProfile.objects.get_or_create(
        user=request.user,
        defaults={'phone': 'Not set', 'age': 25, 'gender': 'Other'}
    )

    user_appointments = Appointment.objects.filter(
        patient=patient_profile
    ).order_by('-appointment_date', '-appointment_time')

    return render(request, 'patient_dashboard.html', {
        'patient': patient_profile,
        'appointments': user_appointments
    })


@login_required(login_url='/login/?role=patient')
def patient_edit_profile_view(request):
    """Allows a patient to update their personal information."""
    patient_profile, _ = PatientProfile.objects.get_or_create(
        user=request.user,
        defaults={'phone': 'Not set', 'age': 25, 'gender': 'Other'}
    )

    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', '').strip()
        request.user.last_name = request.POST.get('last_name', '').strip()
        request.user.email = request.POST.get('email', '').strip()
        request.user.save()

        patient_profile.phone = request.POST.get('phone', patient_profile.phone).strip()
        patient_profile.age = int(request.POST.get('age') or patient_profile.age)
        patient_profile.gender = request.POST.get('gender', patient_profile.gender)
        patient_profile.blood_group = request.POST.get('blood_group', patient_profile.blood_group).strip()
        patient_profile.save()

        return redirect('patient_dashboard')

    return render(request, 'patient_edit_profile.html', {
        'patient': patient_profile
    })


@login_required(login_url='/login/?role=patient')
def cancel_appointment_view(request, appointment_id):
    """Allows patients to cancel only their own scheduled appointments."""
    appointment = get_object_or_404(
        Appointment,
        id=appointment_id,
        patient__user=request.user
    )
    appointment.status = 'Cancelled'
    appointment.save()
    return redirect('patient_dashboard')


# =============================================================
# 4. DOCTOR PORTAL VIEWS (DOCTOR SPECIFIC QUEUE & PROFILE EDIT)
# =============================================================

@login_required(login_url='/login/?role=doctor')
def doctor_dashboard_view(request):
    """Doctor clinical console displaying only appointments booked for this specific doctor."""
    if not hasattr(request.user, 'doctor_profile'):
        return redirect('home')

    current_doctor = request.user.doctor_profile
    my_appointments = Appointment.objects.filter(
        doctor=current_doctor
    ).order_by('appointment_date', 'appointment_time')

    return render(request, 'doctor_dashboard.html', {
        'doctor': current_doctor,
        'appointments': my_appointments
    })


@login_required(login_url='/login/?role=doctor')
def doctor_edit_profile_view(request):
    """Allows a logged-in doctor to update their qualifications, fee, hospital, etc."""
    if not hasattr(request.user, 'doctor_profile'):
        return redirect('home')

    doctor = request.user.doctor_profile
    departments = Department.objects.all()

    if request.method == 'POST':
        request.user.first_name = request.POST.get('first_name', '')
        request.user.last_name = request.POST.get('last_name', '')
        request.user.email = request.POST.get('email', '')
        request.user.save()

        dept_id = request.POST.get('department')
        if dept_id:
            doctor.department = Department.objects.get(id=dept_id)

        doctor.qualification = request.POST.get('qualification', doctor.qualification)
        doctor.experience_years = int(request.POST.get('experience_years') or doctor.experience_years)
        doctor.consultation_fee = float(request.POST.get('consultation_fee') or doctor.consultation_fee)
        doctor.room_number = request.POST.get('room_number', doctor.room_number)
        doctor.clinic_name = request.POST.get('clinic_name', doctor.clinic_name)
        doctor.clinic_address = request.POST.get('clinic_address', doctor.clinic_address)
        doctor.save()

        return redirect('doctor_dashboard')

    return render(request, 'doctor_edit_profile.html', {
        'doctor': doctor,
        'departments': departments
    })


@login_required(login_url='/login/?role=doctor')
def update_appointment_status(request, appointment_id, new_status):
    """Allows doctors to update the status of only their assigned appointments."""
    appointment = get_object_or_404(Appointment, id=appointment_id, doctor__user=request.user)
    if new_status in ['Completed', 'No-Show', 'Cancelled']:
        appointment.status = new_status
        appointment.save()
    return redirect('doctor_dashboard')


# =============================================================
# 5. ADMIN PORTAL VIEWS
# =============================================================

@login_required
def admin_dashboard_view(request):
    """Operational admin dashboard with AI No-Show prediction analytics."""
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('home')

    total_patients = PatientProfile.objects.count()
    total_doctors = DoctorProfile.objects.count()
    total_appointments = Appointment.objects.count()
    doctors = DoctorProfile.objects.all()

    # Retrieve recent appointments and annotate each with AI prediction
    raw_appointments = Appointment.objects.all().order_by('-created_at')[:25]
    
    appointments_with_predictions = []
    high_risk_count = 0

    for app in raw_appointments:
        prediction = calculate_noshow_risk(app)
        if prediction['level'] == 'High' and app.status == 'Scheduled':
            high_risk_count += 1
            
        appointments_with_predictions.append({
            'obj': app,
            'prediction': prediction
        })

    return render(request, 'admin_dashboard.html', {
        'total_patients': total_patients,
        'total_doctors': total_doctors,
        'total_appointments': total_appointments,
        'high_risk_count': high_risk_count,
        'doctors': doctors,
        'appointments': appointments_with_predictions,
    })

@login_required
def admin_edit_doctor_view(request, doctor_id):
    """Allows staff/superusers to modify any doctor's details and hospital affiliation."""
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('home')

    doctor = get_object_or_404(DoctorProfile, id=doctor_id)
    departments = Department.objects.all()

    if request.method == 'POST':
        doctor.user.first_name = request.POST.get('first_name', '')
        doctor.user.last_name = request.POST.get('last_name', '')
        doctor.user.email = request.POST.get('email', '')
        doctor.user.save()

        dept_id = request.POST.get('department')
        if dept_id:
            doctor.department = Department.objects.get(id=dept_id)

        doctor.qualification = request.POST.get('qualification', doctor.qualification)
        doctor.experience_years = int(request.POST.get('experience_years') or doctor.experience_years)
        doctor.consultation_fee = float(request.POST.get('consultation_fee') or doctor.consultation_fee)
        doctor.room_number = request.POST.get('room_number', doctor.room_number)
        doctor.clinic_name = request.POST.get('clinic_name', doctor.clinic_name)
        doctor.clinic_address = request.POST.get('clinic_address', doctor.clinic_address)
        doctor.is_approved = 'is_approved' in request.POST
        doctor.save()

        return redirect('admin_dashboard')

    return render(request, 'admin_edit_doctor.html', {
        'doctor': doctor,
        'departments': departments
    })


@login_required
def toggle_doctor_approval(request, doctor_id):
    """Admin toggle to authorize or suspend doctor listings."""
    if request.user.is_superuser or request.user.is_staff:
        doctor = get_object_or_404(DoctorProfile, id=doctor_id)
        doctor.is_approved = not doctor.is_approved
        doctor.save()
    return redirect('admin_dashboard')

def extract_symptom_tags(symptoms_text):
    """
    Extracts 2-4 clinical symptom tags using llama3.2:1b or keyword heuristics.
    """
    if not symptoms_text:
        return "General Consultation"

    try:
        ollama_url = "http://127.0.0.1:11434/api/chat"
        payload = {
            "model": "llama3.2:1b",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a medical triage assistant. Analyze the patient complaint and extract 2 to 4 concise medical symptom tags. "
                        "Return ONLY the tags separated by commas. Example output: Chest Tightness, Dyspnea, Fatigue"
                    )
                },
                {
                    "role": "user",
                    "content": f"Complaint: {symptoms_text}"
                }
            ],
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 25}
        }
        res = requests.post(ollama_url, json=payload, timeout=6)
        if res.status_code == 200:
            tags = res.json().get('message', {}).get('content', '').strip().replace('.', '')
            if tags:
                return tags
    except Exception as e:
        print(f"[Tags Extraction Error]: {e}")

    # Fallback heuristics if Ollama is unreachable
    tags = []
    text_lower = symptoms_text.lower()
    mapping = {
        'chest': 'Chest Pain', 'breath': 'Dyspnea', 'heart': 'Palpitations',
        'fever': 'Pyrexia', 'skin': 'Rash', 'itch': 'Pruritus',
        'knee': 'Joint Pain', 'bone': 'Musculoskeletal', 'cough': 'Cough',
        'headache': 'Cephalea', 'vomit': 'Emesis', 'nausea': 'Nausea'
    }
    for kw, label in mapping.items():
        if kw in text_lower:
            tags.append(label)

    return ", ".join(tags) if tags else "General Symptoms"