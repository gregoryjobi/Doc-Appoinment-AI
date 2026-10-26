(function ($) {

    "use strict";

    // ==========================================
    // 1. PRELOADER & STELLAR INITIALIZATION
    // ==========================================
    $(window).load(function(){$('.preloader').fadeOut(1000); // set duration in milliseconds
    });

    // Navigation Menu Toggle Fix
    $('.navbar-collapse a').on('click', function(){$(".navbar-collapse").collapse('hide');
    });

    $(window).scroll(function() {
        if ($(".navbar").offset().top > 50) {
            $(".navbar-fixed-top").addClass("top-nav-collapse");
        } else {
            $(".navbar-fixed-top").removeClass("top-nav-collapse");
        }
    });

    // Smooth Scrolling Links
    $('.smoothScroll').on('click', function(event) {
        var $anchor = $(this);$('html, body').stop().animate({
            scrollTop: $($anchor.attr('href')).offset().top - 49
        }, 1000);
        event.preventDefault();
    });

})(jQuery);


// ==========================================
// 2. DYNAMIC GOOGLE MAPS & LOCATION SYNC
// ==========================================

function syncLocationWithMap() {
    const bookingLocationInput = document.getElementById('patient_location');
    const mapLocationInput = document.getElementById('map-location-input');
    const deptSelect = document.getElementById('department-select');
    const mapDeptInput = document.getElementById('map-dept-input');
    const mapFrame = document.getElementById('google-maps-frame');
    const statusText = document.getElementById('map-status-text');

    if (!mapFrame) return;

    // Synchronize both location fields if user typed in either one
    let locationVal = "";
    if (bookingLocationInput && bookingLocationInput.value.trim() !== "") {
        locationVal = bookingLocationInput.value.trim();
        if (mapLocationInput) mapLocationInput.value = locationVal;
    } else if (mapLocationInput && mapLocationInput.value.trim() !== "") {
        locationVal = mapLocationInput.value.trim();
        if (bookingLocationInput) bookingLocationInput.value = locationVal;
    }

    // Determine chosen specialty/department
    let deptVal = "";
    if (deptSelect && deptSelect.value) {
        deptVal = deptSelect.value;
        if (mapDeptInput) mapDeptInput.value = deptVal;
    } else if (mapDeptInput && mapDeptInput.value.trim() !== "") {
        deptVal = mapDeptInput.value.trim();
    }

    // Build targeted Google search query
    let query = "hospital";
    if (deptVal) {
        query = `${deptVal} hospital`;
    }
    if (locationVal) {
        query += ` in ${locationVal}`;
    } else {
        query += " near me";
    }

    if (statusText) {
        statusText.innerHTML = `Google Maps is showing <strong>${deptVal || 'all'}</strong> hospitals closest to <strong>${locationVal || 'your current area'}</strong>.`;
    }

    // Update iframe embed source dynamically
    mapFrame.src = `https://maps.google.com/maps?q=${encodeURIComponent(query)}&t=&z=14&ie=UTF8&iwloc=&output=embed`;
}

// GPS "Detect" button handler
function detectCurrentLocation() {
    if (navigator.geolocation) {
        const statusText = document.getElementById('map-status-text');
        if (statusText) statusText.innerHTML = "Detecting your current coordinates...";

        navigator.geolocation.getCurrentPosition(function (position) {
            const lat = position.coords.latitude;
            const lng = position.coords.longitude;
            
            const bookingLoc = document.getElementById('patient_location');
            if (bookingLoc) bookingLoc.value = "Current Location";

            const mapLoc = document.getElementById('map-location-input');
            if (mapLoc) mapLoc.value = "Current Location";

            const deptSelect = document.getElementById('department-select');
            const deptVal = deptSelect ? deptSelect.value : "";
            const query = deptVal ? `${deptVal} hospital` : "hospital";

            // Center directly onto user's GPS latitude and longitude
            const mapFrame = document.getElementById('google-maps-frame');
            if (mapFrame) {
                mapFrame.src = `https://maps.google.com/maps?q=${encodeURIComponent(query)}&ll=${lat},${lng}&z=14&output=embed`;
            }

            if (statusText) {
                statusText.innerHTML = `Google Maps is showing <strong>${deptVal || 'all'}</strong> hospitals around your GPS position.`;
            }
        }, function (error) {
            alert("Could not retrieve GPS position. Please enter your city/neighborhood manually.");
        });
    }
}


// ==========================================
// DOCTOR RETRIEVAL & HOSPITAL AUTO-FILL
// ==========================================

function updateHospitalField() {
    const doctorSelect = document.getElementById('doctor-select');
    const hospitalInput = document.getElementById('hospital_name_display');
    if (!doctorSelect || !hospitalInput) return;

    const selectedOption = doctorSelect.options[doctorSelect.selectedIndex];
    if (selectedOption && selectedOption.dataset.hospital) {
        const hospitalName = selectedOption.dataset.hospital;
        const hospitalAddress = selectedOption.dataset.address;
        hospitalInput.value = `${hospitalName} (${hospitalAddress})`;
    } else {
        hospitalInput.value = "";
    }
}

function onDoctorChange() {
    updateHospitalField();
}

function loadDoctorsForDepartment(departmentName, autoSelectTopDoctor = false) {
    const doctorSelect = document.getElementById('doctor-select');
    const hospitalInput = document.getElementById('hospital_name_display');
    if (!doctorSelect) return;

    doctorSelect.innerHTML = '<option value="">Loading available doctors...</option>';
    if (hospitalInput) hospitalInput.value = "";

    fetch(`/api/get-doctors-by-dept/?department=${encodeURIComponent(departmentName)}`)
        .then(response => response.json())
        .then(data => {
            doctorSelect.innerHTML = '';
            if (data.doctors && data.doctors.length > 0) {
                doctorSelect.innerHTML = '<option value="">-- Choose a Doctor --</option>';
                data.doctors.forEach((doc, index) => {
                    const opt = document.createElement('option');
                    opt.value = doc.id;
                    opt.textContent = `${doc.name} (${doc.qualification}) - ${doc.experience} yrs exp - $${doc.fee}`;
                    
                    // Attach hospital info as dataset attributes
                    opt.dataset.hospital = doc.hospital_name;
                    opt.dataset.address = doc.hospital_address;

                    // Automatically pick the most experienced doctor if requested
                    if (autoSelectTopDoctor && index === 0) {
                        opt.selected = true;
                    }
                    doctorSelect.appendChild(opt);
                });

                // Update the hospital field right away if a doctor was selected
                updateHospitalField();
            } else {
                doctorSelect.innerHTML = '<option value="">No doctors found in this department</option>';
                if (hospitalInput) hospitalInput.value = "No affiliated hospital available";
            }
        })
        .catch(err => {
            console.error("Error loading doctors:", err);
            doctorSelect.innerHTML = '<option value="">Error loading doctors</option>';
        });
}


// ==========================================
// 4. AI SYMPTOM ANALYSIS PIPELINE
// ==========================================

window.predictDepartment = function(event) {
    if (event) event.preventDefault();
    
    // 1. Get the symptom text from the AI input box
    const symptomInput = document.getElementById('symptoms');
    const symptomText = symptomInput ? symptomInput.value.trim() : '';

    if (!symptomText) {
        alert("Please describe your symptoms first.");
        return;
    }

    fetch('/api/predict-department', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symptoms: symptomText })
    })
    .then(response => response.json())
    .then(data => {
        // Show AI Prediction Card
        const aiCard = document.getElementById('ai-prediction-card');
        if (aiCard) aiCard.style.display = 'block';

        const predDeptEl = document.getElementById('predicted-department');
        if (predDeptEl) predDeptEl.innerText = data.department;

        // Auto-fill hidden input for form submission
        const aiHidden = document.getElementById('ai-dept-hidden');
        if (aiHidden) aiHidden.value = data.department;

        // Auto-fill symptoms into the booking form
        const bookingSymptoms = document.getElementById('booking_symptoms');
        if (bookingSymptoms) {
            bookingSymptoms.value = symptomText;
        }

        // Auto-select department in the appointment form dropdown
        const deptSelect = document.getElementById('department-select');
        if (deptSelect) {
            for (let i = 0; i < deptSelect.options.length; i++) {
                if (deptSelect.options[i].text.toLowerCase().includes(data.department.toLowerCase())) {
                    deptSelect.selectedIndex = i;
                    break;
                }
            }
        }

        // Auto-fetch doctors and select the one with highest experience
        loadDoctorsForDepartment(data.department, true);

        // Sync Google Maps locator
        const mapDeptInput = document.getElementById('map-dept-input');
        if (mapDeptInput) mapDeptInput.value = data.department;
        syncLocationWithMap();

        // Smooth scroll to the appointment form
        const aptSection = document.getElementById('appointment');
        if (aptSection) {
            aptSection.scrollIntoView({ behavior: 'smooth' });
        }
    })
    .catch(err => console.error("Error predicting department:", err));
};

// Check if user came from the Patient Dashboard AI Triage
document.addEventListener("DOMContentLoaded", function() {
    const savedDept = sessionStorage.getItem('triage_department');
    const savedSymptoms = sessionStorage.getItem('triage_symptoms');

    if (savedDept) {
        // Pre-fill symptoms
        const bookingSymptoms = document.getElementById('booking_symptoms');
        if (bookingSymptoms && savedSymptoms) {
            bookingSymptoms.value = savedSymptoms;
        }

        // Set department dropdown
        const deptSelect = document.getElementById('department-select');
        if (deptSelect) {
            for (let i = 0; i < deptSelect.options.length; i++) {
                if (deptSelect.options[i].text.toLowerCase().includes(savedDept.toLowerCase())) {
                    deptSelect.selectedIndex = i;
                    break;
                }
            }
        }

        // Auto-select the top doctor by experience
        if (typeof loadDoctorsForDepartment === 'function') {
            loadDoctorsForDepartment(savedDept, true);
        }

        // Clean up session storage so it doesn't trigger on subsequent ordinary visits
        sessionStorage.removeItem('triage_department');
        sessionStorage.removeItem('triage_symptoms');
    }
});