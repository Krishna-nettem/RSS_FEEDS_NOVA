document.addEventListener('DOMContentLoaded', function() {
    // For each category, set up dropdown and select/deselect all
    document.querySelectorAll('.category-toggle').forEach(function(toggleBtn) {
        toggleBtn.addEventListener('click', function() {
            const cat = this.dataset.cat;
            const dropdown = document.getElementById('dropdown-' + cat);
            dropdown.classList.toggle('hidden');
        });
    });

    document.querySelectorAll('.category-plus').forEach(function(plusBtn) {
        plusBtn.addEventListener('click', function() {
            const cat = this.dataset.cat;
            const dropdown = document.getElementById('dropdown-' + cat);
            dropdown.classList.remove('hidden');
            document.querySelectorAll('.subcat-checkbox[data-cat="' + cat + '"]').forEach(function(cb) {
                cb.checked = true;
            });
        });
    });

    document.querySelectorAll('.category-minus').forEach(function(minusBtn) {
        minusBtn.addEventListener('click', function() {
            const cat = this.dataset.cat;
            document.querySelectorAll('.subcat-checkbox[data-cat="' + cat + '"]').forEach(function(cb) {
                cb.checked = false;
            });
        });
    });

    document.querySelectorAll('.subcat-plus').forEach(function(plusBtn) {
        plusBtn.addEventListener('click', function() {
            const subcat = this.dataset.subcat;
            document.getElementById('cb-' + subcat).checked = true;
        });
    });
    document.querySelectorAll('.subcat-minus').forEach(function(minusBtn) {
        minusBtn.addEventListener('click', function() {
            const subcat = this.dataset.subcat;
            document.getElementById('cb-' + subcat).checked = false;
        });
    });
});
