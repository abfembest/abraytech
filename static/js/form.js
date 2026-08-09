document.addEventListener('DOMContentLoaded', function() {
    let currentStep = 1;
    const totalSteps = 4; // Only 4 interactive steps
    
    const stepTitles = {
        1: "Personal Information",
        2: "Academic History",
        3: "Course Selection",
        4: "Review & Save"
    };
    
    // Get CSRF token
    const CSRF_TOKEN = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    
    // DOM Elements
    const form = document.getElementById('applicationForm');
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const nextBtnText = document.getElementById('nextBtnText');
    const progressSteps = document.querySelectorAll('.progress-step');
    const formSteps = document.querySelectorAll('.form-step');
    
    // Progress indicators
    const progressBar = document.getElementById('progressBar');
    const mobileProgressBar = document.getElementById('mobileProgressBar');
    const stepProgressBar = document.getElementById('stepProgressBar');
    const progressPercentage = document.getElementById('progressPercentage');
    const mobileProgressPercentage = document.getElementById('mobileProgressPercentage');
    const currentStepElement = document.getElementById('mobileCurrentStep');
    const stepTitleElement = document.getElementById('stepTitle');
    const mobileStepTitleElement = document.getElementById('mobileStepTitle');
    
    // Academic entries management
    let academicEntryCount = 0;
    
    // ================= ACADEMIC ENTRIES =================
    function addAcademicEntry() {
        academicEntryCount++;
        const container = document.getElementById('academicEntriesContainer');
        
        const entryHTML = `
            <div class="academic-entry border-2 border-gray-300 rounded-lg p-6 relative" data-entry="${academicEntryCount}">
                ${academicEntryCount > 1 ? `
                <button type="button" class="remove-entry absolute top-4 right-4 text-red-600 hover:text-red-800" onclick="removeAcademicEntry(${academicEntryCount})">
                    <i data-lucide="x-circle" class="w-6 h-6"></i>
                </button>
                ` : ''}
                
                <h4 class="font-semibold mb-4 text-gray-800">Academic Entry ${academicEntryCount}</h4>
                
                <div class="grid md:grid-cols-2 gap-6 mb-6">
                    <div>
                        <label class="block text-gray-700 font-medium mb-2">
                            Education Level <span class="text-red-500">*</span>
                        </label>
                        <select name="education_level_${academicEntryCount}" required class="w-full p-3 border-2 border-gray-300 rounded-lg focus:border-purple-500 bg-white">
                            <option value="">-- Select Level --</option>
                            <option value="high-school">High School</option>
                            <option value="bachelor">Bachelor's Degree</option>
                            <option value="master">Master's Degree</option>
                            <option value="phd">PhD/Doctorate</option>
                        </select>
                    </div>
                    
                    <div>
                        <label class="block text-gray-700 font-medium mb-2">
                            Graduation Year <span class="text-red-500">*</span>
                        </label>
                        <input type="number" name="graduation_year_${academicEntryCount}" required min="1950" max="2030" placeholder="2023" class="w-full p-3 border-2 border-gray-300 rounded-lg focus:border-purple-500">
                    </div>
                </div>
                
                <div class="mb-6">
                    <label class="block text-gray-700 font-medium mb-2">
                        Institution Name <span class="text-red-500">*</span>
                    </label>
                    <input type="text" name="institution_${academicEntryCount}" required placeholder="University/College Name" class="w-full p-3 border-2 border-gray-300 rounded-lg focus:border-purple-500">
                </div>
                
                <div class="grid md:grid-cols-2 gap-6">
                    <div>
                        <label class="block text-gray-700 font-medium mb-2">
                            Field of Study <span class="text-red-500">*</span>
                        </label>
                        <input type="text" name="field_of_study_${academicEntryCount}" required placeholder="Major/Field of Study" class="w-full p-3 border-2 border-gray-300 rounded-lg focus:border-purple-500">
                    </div>
                    
                    <div>
                        <label class="block text-gray-700 font-medium mb-2">
                            GPA (Optional)
                        </label>
                        <input type="text" name="gpa_${academicEntryCount}" placeholder="3.5/4.0" class="w-full p-3 border-2 border-gray-300 rounded-lg focus:border-purple-500">
                    </div>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('beforeend', entryHTML);
        if (typeof lucide !== 'undefined') lucide.createIcons();
        
        // Add event listeners to new inputs
        const newEntry = container.querySelector(`[data-entry="${academicEntryCount}"]`);
        const newInputs = newEntry.querySelectorAll('input, select, textarea');
        newInputs.forEach(input => {
            addInputListeners(input);
        });
    }
    
    window.removeAcademicEntry = function(entryId) {
        const entry = document.querySelector(`.academic-entry[data-entry="${entryId}"]`);
        if (entry && academicEntryCount > 1) {
            entry.remove();
        }
    };
    
    // Add button listener
    const addAcademicBtn = document.getElementById('addAcademicEntryBtn');
    if (addAcademicBtn) {
        addAcademicBtn.addEventListener('click', addAcademicEntry);
    }
    
    // ================= NAVIGATION =================
    function goToNextStep() {
        // If on step 4, save the application instead of going to next step
        if (currentStep === totalSteps) {
            saveApplication();
            return;
        }
        
        if (validateStep(currentStep)) {
            if (currentStep < totalSteps) {
                currentStep++;
                updateStep();
            }
        }
    }
    
    function goToPrevStep() {
        if (currentStep > 1) {
            currentStep--;
            updateStep();
        }
    }
    
    // ================= STEP UPDATE =================
    function updateStep() {
        // Update titles
        const title = stepTitles[currentStep];
        if (stepTitleElement) stepTitleElement.textContent = title;
        if (mobileStepTitleElement) mobileStepTitleElement.textContent = title;
        if (currentStepElement) currentStepElement.textContent = currentStep;
        
        // Update button text based on current step
        if (nextBtnText) {
            if (currentStep === totalSteps) {
                nextBtnText.innerHTML = '<span class="flex items-center gap-2"><span>Save & Continue</span><i data-lucide="check" class="w-4 h-4"></i></span>';
                if (typeof lucide !== 'undefined') lucide.createIcons();
            } else {
                nextBtnText.textContent = 'Next Step →';
            }
        }
        
        // Update progress steps
        progressSteps.forEach(step => {
            const stepNum = parseInt(step.getAttribute('data-step'));
            step.classList.remove('active', 'completed');
            
            if (stepNum < currentStep) {
                step.classList.add('completed');
            } else if (stepNum === currentStep) {
                step.classList.add('active');
            }
        });
        
        // Update form step visibility
        formSteps.forEach((step, index) => {
            if (index + 1 === currentStep) {
                step.classList.add('active');
            } else {
                step.classList.remove('active');
            }
        });
        
        // Update buttons
        if (prevBtn) prevBtn.classList.toggle('hidden', currentStep === 1);
        
        // Update progress bars
        const progressPercent = ((currentStep - 1) / (totalSteps - 1)) * 100;
        if (progressBar) progressBar.style.width = `${progressPercent}%`;
        if (mobileProgressBar) mobileProgressBar.style.width = `${progressPercent}%`;
        if (stepProgressBar) stepProgressBar.style.width = `${progressPercent}%`;
        
        const percentText = Math.round(progressPercent);
        if (progressPercentage) progressPercentage.textContent = percentText;
        if (mobileProgressPercentage) mobileProgressPercentage.textContent = percentText;
        
        // Update review section if on step 4
        if (currentStep === 4) {
            updateReviewSection();
        }
        
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    
    // ================= VALIDATION =================
    function validateStep(step) {
        const activeStep = document.getElementById(`step${step}`);
        if (!activeStep) return false;
        
        let isValid = true;
        const inputs = activeStep.querySelectorAll('input[required], select[required], textarea[required]');
        
        // Clear previous error states
        inputs.forEach(input => {
            input.classList.remove('border-red-500');
            // Remove any existing error messages
            const errorDiv = input.parentElement.querySelector('.text-red-500');
            if (errorDiv && errorDiv.classList.contains('validation-error')) {
                errorDiv.remove();
            }
        });
        
        inputs.forEach(input => {
            let fieldIsValid = true;
            
            if (input.type === 'checkbox') {
                // For checkboxes (declarations), check if checked
                if (input.hasAttribute('required') && !input.checked) {
                    fieldIsValid = false;
                }
            } else if (input.tagName === 'SELECT') {
                // For dropdowns, check if a valid option is selected
                if (!input.value || input.value === '' || input.value === '--------') {
                    fieldIsValid = false;
                }
            } else if (input.type === 'date') {
                // For date fields, check if value exists
                if (!input.value) {
                    fieldIsValid = false;
                }
            } else {
                // For text inputs, check if value exists and is not just whitespace
                if (!input.value || !input.value.trim()) {
                    fieldIsValid = false;
                }
            }
            
            if (!fieldIsValid) {
                isValid = false;
                input.classList.add('border-red-500');
                
                // Add inline error message if it doesn't exist
                const existingError = input.parentElement.querySelector('.validation-error');
                if (!existingError) {
                    const errorMsg = document.createElement('div');
                    errorMsg.className = 'text-red-500 text-sm mt-1 validation-error';
                    errorMsg.textContent = 'This field is required';
                    input.parentElement.appendChild(errorMsg);
                }
            } else {
                input.classList.remove('border-red-500');
            }
        });
        
        if (!isValid) {
            // Scroll to first error
            const firstError = activeStep.querySelector('.border-red-500');
            if (firstError) {
                firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
        
        return isValid;
    }
    
    // ================= SERIALIZE ACADEMIC HISTORY =================
    function serializeAcademicHistory() {
        const entries = [];
        const academicEntries = document.querySelectorAll('.academic-entry');
        
        academicEntries.forEach(entry => {
            const entryId = entry.getAttribute('data-entry');
            const degree = entry.querySelector(`select[name="education_level_${entryId}"]`)?.value || '';
            const institution = entry.querySelector(`input[name="institution_${entryId}"]`)?.value || '';
            const graduationYear = entry.querySelector(`input[name="graduation_year_${entryId}"]`)?.value || '';
            const fieldOfStudy = entry.querySelector(`input[name="field_of_study_${entryId}"]`)?.value || '';
            const gpa = entry.querySelector(`input[name="gpa_${entryId}"]`)?.value || '';
            
            if (degree || institution || graduationYear || fieldOfStudy) {
                entries.push({
                    degree: degree,
                    institution: institution,
                    graduation_year: graduationYear,
                    field_of_study: fieldOfStudy,
                    gpa: gpa
                });
            }
        });
        
        document.getElementById('academicHistoryPayload').value = JSON.stringify(entries);
    }
    
    // ================= REVIEW SECTION =================
    function updateReviewSection() {
        const reviewSummary = document.getElementById('reviewSummary');
        if (!reviewSummary) return;
        
        const formData = new FormData(form);
        
        const firstName = formData.get('first_name') || '';
        const lastName = formData.get('last_name') || '';
        const email = formData.get('email') || '';
        const phone = formData.get('phone') || '';
        const country = form.querySelector('select[name="country"]')?.selectedOptions[0]?.text || 'Not selected';
        const program = form.querySelector('select[name="course"]')?.selectedOptions[0]?.text || 'Not selected';
        
        let academicHTML = '';
        for (let i = 1; i <= academicEntryCount; i++) {
            const level = formData.get(`education_level_${i}`);
            const institution = formData.get(`institution_${i}`);
            if (level && institution) {
                academicHTML += `<p>Entry ${i}: ${level} at ${institution}</p>`;
            }
        }
        
        let summaryHTML = `
            <div class="mb-4">
                <h4 class="font-semibold mb-2 text-purple-900">Personal Information</h4>
                <p class="text-gray-700">Name: ${firstName} ${lastName}</p>
                <p class="text-gray-700">Email: ${email}</p>
                <p class="text-gray-700">Phone: ${phone}</p>
                <p class="text-gray-700">Country: ${country}</p>
            </div>
            
            <div class="mb-4">
                <h4 class="font-semibold mb-2 text-purple-900">Academic History</h4>
                ${academicHTML || '<p class="text-gray-700">Not provided</p>'}
            </div>
            
            <div class="mb-4">
                <h4 class="font-semibold mb-2 text-purple-900">Program Selection</h4>
                <p class="text-gray-700">Program: ${program}</p>
            </div>
        `;
        
        reviewSummary.innerHTML = summaryHTML;
    }
    
    // ================= SAVE APPLICATION =================
    function saveApplication() {
        // Validate all steps before saving
        let allValid = true;
        for (let i = 1; i <= 3; i++) {
            if (!validateStep(i)) {
                allValid = false;
                // Switch to the first invalid step
                currentStep = i;
                updateStep();
                break;
            }
        }
        
        if (!allValid) {
            return;
        }
        
        const originalHTML = nextBtn.innerHTML;
        nextBtn.disabled = true;
        nextBtn.innerHTML = '⏳ Saving...';
        
        serializeAcademicHistory();
        
        const formData = new FormData(form);
        
        fetch('/applications/save-draft/', {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (data.application_id) {
                    document.getElementById('applicationId').value = data.application_id;
                }
                
                // Redirect to application status page
                window.location.href = '/application_status/';
            } else {
                throw new Error(data.error || 'Save failed');
            }
        })
        .catch(error => {
            console.error('Save error:', error);
            nextBtn.disabled = false;
            nextBtn.innerHTML = originalHTML;
        });
    }
    
    // ================= INPUT LISTENERS =================
    function addInputListeners(input) {
        input.addEventListener('input', function() {
            this.classList.remove('border-red-500');
            const errorMsg = this.parentElement.querySelector('.validation-error');
            if (errorMsg) {
                errorMsg.remove();
            }
        });
        
        input.addEventListener('change', function() {
            this.classList.remove('border-red-500');
            const errorMsg = this.parentElement.querySelector('.validation-error');
            if (errorMsg) {
                errorMsg.remove();
            }
        });
    }
    
    // ================= EVENT LISTENERS =================
    if (prevBtn) prevBtn.addEventListener('click', goToPrevStep);
    if (nextBtn) nextBtn.addEventListener('click', goToNextStep);
    
    // Progress step click handlers (only for steps 1-4)
    progressSteps.forEach(step => {
        step.addEventListener('click', function() {
            const stepNum = parseInt(this.getAttribute('data-step'));
            if (stepNum <= totalSteps && !this.classList.contains('disabled')) {
                if (stepNum < currentStep || validateStep(currentStep)) {
                    currentStep = stepNum;
                    updateStep();
                }
            }
        });
    });
    
    // English proficiency score visibility
    const englishTest = document.querySelector('select[name="english_proficiency_test"]');
    const scoreContainer = document.getElementById('scoreContainer');
    if (englishTest && scoreContainer) {
        englishTest.addEventListener('change', function() {
            if (this.value && this.value !== 'native' && this.value !== '') {
                scoreContainer.style.display = 'block';
            } else {
                scoreContainer.style.display = 'none';
            }
        });
    }
    
    // ================= INITIALIZATION =================
    function initForm() {
        addAcademicEntry();
        updateStep();
        if (typeof lucide !== 'undefined') lucide.createIcons();
        
        // Add input event listeners to clear errors on user input
        const allInputs = form.querySelectorAll('input, select, textarea');
        allInputs.forEach(input => {
            addInputListeners(input);
        });
    }
    
    initForm();
});