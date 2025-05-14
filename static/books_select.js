// Books selection page enhancement
document.addEventListener('DOMContentLoaded', function() {
    // For each category, set up dropdown and select/deselect all
    document.querySelectorAll('.category-toggle').forEach(function(toggleBtn) {
        toggleBtn.addEventListener('click', function() {
            const cat = this.dataset.cat;
            const dropdown = document.getElementById('dropdown-' + cat);
            dropdown.classList.toggle('hidden');
            
            // Change arrow icon
            const arrowIcon = this;
            const isCollapsed = dropdown.classList.contains('hidden');
            arrowIcon.innerHTML = isCollapsed ? '&#9660;' : '&#9650;';
            
            // Add animation for dropdown
            if (!dropdown.classList.contains('hidden')) {
                const subcategories = dropdown.querySelectorAll('.subcategory');
                subcategories.forEach((item, index) => {
                    item.style.opacity = '0';
                    item.style.transform = 'translateY(10px)';
                    
                    setTimeout(() => {
                        item.style.transition = 'all 0.3s ease-out';
                        item.style.opacity = '1';
                        item.style.transform = 'translateY(0)';
                    }, 50 * index);
                });
            }
        });
    });

    document.querySelectorAll('.category-plus').forEach(function(plusBtn) {
        plusBtn.addEventListener('click', function() {
            const cat = this.dataset.cat;
            const dropdown = document.getElementById('dropdown-' + cat);
            dropdown.classList.remove('hidden');
            
            // Update arrow icon
            const toggleBtn = document.querySelector(`.category-toggle[data-cat="${cat}"]`);
            toggleBtn.innerHTML = '&#9650;';
            
            document.querySelectorAll('.subcat-checkbox[data-cat="' + cat + '"]').forEach(function(cb) {
                cb.checked = true;
                updateCheckboxStyle(cb);
            });
        });
    });

    document.querySelectorAll('.category-minus').forEach(function(minusBtn) {
        minusBtn.addEventListener('click', function() {
            const cat = this.dataset.cat;
            document.querySelectorAll('.subcat-checkbox[data-cat="' + cat + '"]').forEach(function(cb) {
                cb.checked = false;
                updateCheckboxStyle(cb);
            });
        });
    });

    document.querySelectorAll('.subcat-plus').forEach(function(plusBtn) {
        plusBtn.addEventListener('click', function() {
            const subcat = this.dataset.subcat;
            const checkbox = document.getElementById('cb-' + subcat);
            checkbox.checked = true;
            updateCheckboxStyle(checkbox);
        });
    });
    
    document.querySelectorAll('.subcat-minus').forEach(function(minusBtn) {
        minusBtn.addEventListener('click', function() {
            const subcat = this.dataset.subcat;
            const checkbox = document.getElementById('cb-' + subcat);
            checkbox.checked = false;
            updateCheckboxStyle(checkbox);
        });
    });
    
    // Add visual feedback when checking/unchecking
    const checkboxes = document.querySelectorAll('.subcat-checkbox');
    checkboxes.forEach(checkbox => {
        // Initial state
        updateCheckboxStyle(checkbox);
        
        // Listen for changes
        checkbox.addEventListener('change', function() {
            updateCheckboxStyle(this);
        });
    });
    
    function updateCheckboxStyle(checkbox) {
        const subcategory = checkbox.closest('.subcategory');
        
        if (checkbox.checked) {
            subcategory.style.backgroundColor = '#f0f8ff';
            subcategory.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
        } else {
            subcategory.style.backgroundColor = '';
            subcategory.style.boxShadow = '';
        }
    }
    
    // Add shine effect to submit button
    const submitBtn = document.querySelector('.submit-btn');
    if (submitBtn) {
        submitBtn.addEventListener('mouseover', function() {
            this.style.background = 'linear-gradient(90deg, #3498db, #2980b9, #3498db)';
            this.style.backgroundSize = '200% 100%';
            this.style.animation = 'shine 2s infinite';
        });
        
        submitBtn.addEventListener('mouseout', function() {
            this.style.background = '#3498db';
            this.style.animation = 'none';
        });
    }
});

// Add shine animation
const style = document.createElement('style');
style.innerHTML = `
@keyframes shine {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}`;
document.head.appendChild(style);
