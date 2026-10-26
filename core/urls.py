from django.urls import path
from . import views

urlpatterns = [
    # Public & Landing
    path('', views.index_view, name='home'),
    path('book-appointment/', views.book_appointment_view, name='book_appointment'),

    # APIs
    path('api/predict-department', views.predict_department_api, name='predict_department'),
    path('api/get-doctors-by-dept/', views.get_doctors_by_department_api, name='get_doctors_by_dept'),
    path('api/nearby-hospitals/', views.nearby_hospitals_api, name='nearby_hospitals'),

    # Authentication & Registration
    path('login/', views.user_login_view, name='login'),
    path('logout/', views.user_logout_view, name='logout'),
    path('register/patient/', views.patient_register_view, name='register_patient'),
    path('register/doctor/', views.doctor_register_view, name='register_doctor'),

    # Patient Portal
    path('patient/dashboard/', views.patient_dashboard_view, name='patient_dashboard'),
    path('patient/profile/edit/', views.patient_edit_profile_view, name='patient_edit_profile'),
    path('appointment/<int:appointment_id>/cancel/', views.cancel_appointment_view, name='cancel_appointment'),

    # Doctor Portal
    path('doctor/dashboard/', views.doctor_dashboard_view, name='doctor_dashboard'),
    path('doctor/profile/edit/', views.doctor_edit_profile_view, name='doctor_edit_profile'),
    path('appointment/<int:appointment_id>/status/<str:new_status>/', views.update_appointment_status, name='update_appointment_status'),

    # Admin Portal
    path('admin-portal/dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin-portal/doctor/<int:doctor_id>/edit/', views.admin_edit_doctor_view, name='admin_edit_doctor'),
    path('admin-portal/doctor/<int:doctor_id>/toggle-approval/', views.toggle_doctor_approval, name='toggle_doctor_approval'),
]