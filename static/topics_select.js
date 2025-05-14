// Topics selection page enhancement
document.addEventListener('DOMContentLoaded', function() {
    // Add animation when loading the page
    const topicItems = document.querySelectorAll('.topic-item');
    
    topicItems.forEach((item, index) => {
        // Add staggered animation
        item.style.opacity = '0';
        item.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            item.style.transition = 'all 0.5s ease-out';
            item.style.opacity = '1';
            item.style.transform = 'translateY(0)';
        }, 100 + (index * 50));
    });
    
    // Add highlight effect to selected items
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    
    checkboxes.forEach(checkbox => {
        // Initial state
        updateCheckboxStyle(checkbox);
        
        // Listen for changes
        checkbox.addEventListener('change', function() {
            updateCheckboxStyle(this);
        });
    });
    
    function updateCheckboxStyle(checkbox) {
        const parentItem = checkbox.closest('.topic-item');
        
        if (checkbox.checked) {
            parentItem.style.backgroundColor = checkbox.classList.contains('arxiv-label') ? 
                'rgba(231, 76, 60, 0.1)' : 'rgba(155, 89, 182, 0.1)';
            parentItem.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
            parentItem.style.transform = 'translateY(-2px)';
        } else {
            parentItem.style.backgroundColor = '';
            parentItem.style.boxShadow = '';
            parentItem.style.transform = '';
        }
    }
});
