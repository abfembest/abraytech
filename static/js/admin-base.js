// Admin Base JavaScript
document.addEventListener('DOMContentLoaded', function() {
    initSidebar();
    initMenuToggles();
    initResponsiveHandling();
    initChatbot();
    initHeaderDropdowns();
});

function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('toggleSidebar');
    const closeBtn = document.getElementById('closeSidebar');
    const mainContent = document.querySelector('.flex-1.flex.flex-col.min-h-screen');

    if (toggleBtn) {
        toggleBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            
            if (window.innerWidth >= 768) {
                // Desktop: Toggle collapsed state
                sidebar.classList.toggle('sidebar-collapsed');
            } else {
                // Mobile: Toggle visibility
                sidebar.classList.toggle('-translate-x-full');
            }
            
            const isExpanded = !sidebar.classList.contains('-translate-x-full') && !sidebar.classList.contains('sidebar-collapsed');
            toggleBtn.setAttribute('aria-expanded', isExpanded);
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', function() {
            sidebar.classList.add('-translate-x-full');
            if (toggleBtn) {
                toggleBtn.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function(e) {
        if (window.innerWidth < 768) {
            const isClickInsideSidebar = sidebar.contains(e.target);
            const isClickOnToggle = toggleBtn && toggleBtn.contains(e.target);
            
            if (!isClickInsideSidebar && !isClickOnToggle && !sidebar.classList.contains('-translate-x-full')) {
                sidebar.classList.add('-translate-x-full');
                if (toggleBtn) {
                    toggleBtn.setAttribute('aria-expanded', 'false');
                }
            }
        }
    });
}

function initMenuToggles() {
    const menuToggles = document.querySelectorAll('.menu-toggle');
    
    menuToggles.forEach(toggle => {
        toggle.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('data-target');
            const targetMenu = document.getElementById(targetId);
            const arrow = this.querySelector('.menu-arrow');
            const isExpanded = this.getAttribute('aria-expanded') === 'true';

            // Close other menus
            document.querySelectorAll('[id$="Menu"]').forEach(menu => {
                if (menu.id !== targetId) {
                    menu.style.maxHeight = '0';
                    const otherToggle = document.querySelector(`[data-target="${menu.id}"]`);
                    if (otherToggle) {
                        otherToggle.setAttribute('aria-expanded', 'false');
                        const otherArrow = otherToggle.querySelector('.menu-arrow');
                        if (otherArrow) {
                            otherArrow.style.transform = 'rotate(0deg)';
                        }
                    }
                }
            });

            // Toggle current menu
            if (isExpanded) {
                targetMenu.style.maxHeight = '0';
                this.setAttribute('aria-expanded', 'false');
                if (arrow) arrow.style.transform = 'rotate(0deg)';
            } else {
                targetMenu.style.maxHeight = targetMenu.scrollHeight + 'px';
                this.setAttribute('aria-expanded', 'true');
                if (arrow) arrow.style.transform = 'rotate(90deg)';
            }
        });
    });

    // Auto-expand menu if current page is in submenu
    const currentPath = window.location.pathname;
    menuToggles.forEach(toggle => {
        const targetId = toggle.getAttribute('data-target');
        const targetMenu = document.getElementById(targetId);
        const links = targetMenu.querySelectorAll('a');
        
        links.forEach(link => {
            if (link.getAttribute('href') === currentPath) {
                targetMenu.style.maxHeight = targetMenu.scrollHeight + 'px';
                toggle.setAttribute('aria-expanded', 'true');
                const arrow = toggle.querySelector('.menu-arrow');
                if (arrow) arrow.style.transform = 'rotate(90deg)';
            }
        });
    });
}

function initResponsiveHandling() {
    const sidebar = document.getElementById('sidebar');
    
    window.addEventListener('resize', function() {
        if (window.innerWidth >= 768) {
            sidebar.classList.remove('-translate-x-full');
        } else {
            sidebar.classList.add('-translate-x-full');
        }
    });
}

// Chatbot Functions
function initChatbot() {
    const chatbotToggle = document.getElementById('chatbotToggle');
    const chatbotWindow = document.getElementById('chatbotWindow');
    const chatbotClose = document.getElementById('chatbotClose');
    const chatbotInput = document.getElementById('chatbotInput');
    const sendMessageBtn = document.getElementById('sendMessage');
    const quickReplyBtns = document.querySelectorAll('.quick-reply-btn');

    if (chatbotToggle) {
        chatbotToggle.addEventListener('click', function() {
            chatbotWindow.classList.toggle('hidden');
        });
    }

    if (chatbotClose) {
        chatbotClose.addEventListener('click', function() {
            chatbotWindow.classList.add('hidden');
        });
    }

    if (sendMessageBtn) {
        sendMessageBtn.addEventListener('click', sendChatMessage);
    }

    if (chatbotInput) {
        chatbotInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendChatMessage();
            }
        });
    }

    quickReplyBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const message = this.textContent;
            addUserMessage(message);
            handleQuickReply(message);
        });
    });
}

function initHeaderDropdowns() {
    // Notifications dropdown
    const notificationBtn = document.querySelector('[aria-label="Notifications"]');
    const notificationDropdown = notificationBtn?.nextElementSibling;
    
    if (notificationBtn && notificationDropdown) {
        notificationBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            notificationDropdown.classList.toggle('hidden');
            // Close user dropdown
            userDropdown?.classList.add('hidden');
        });
    }
    
    // User profile dropdown
    const userBtn = document.querySelector('[aria-haspopup="true"]').parentElement.querySelector('button');
    const userDropdown = userBtn?.nextElementSibling;
    
    if (userBtn && userDropdown) {
        userBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            userDropdown.classList.toggle('hidden');
            // Close notification dropdown
            notificationDropdown?.classList.add('hidden');
        });
    }
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', function() {
        notificationDropdown?.classList.add('hidden');
        userDropdown?.classList.add('hidden');
    });
}

function sendChatMessage() {
    const input = document.getElementById('chatbotInput');
    const message = input.value.trim();
    
    if (message) {
        addUserMessage(message);
        input.value = '';
        
        // Simulate bot response
        setTimeout(() => {
            addBotMessage("I understand. Let me help you with that.");
        }, 1000);
    }
}

function addUserMessage(text) {
    const messagesContainer = document.getElementById('chatbotMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'mb-4 text-right';
    messageDiv.innerHTML = `
        <div class="inline-block max-w-[80%] bg-primary-600 text-white rounded-2xl rounded-tr-none p-4">
            <p>${text}</p>
        </div>
    `;
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function addBotMessage(text) {
    const messagesContainer = document.getElementById('chatbotMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'mb-4';
    messageDiv.innerHTML = `
        <div class="inline-block max-w-[80%] bg-gray-100 rounded-2xl rounded-tl-none p-4">
            <p class="text-gray-800">${text}</p>
        </div>
    `;
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function handleQuickReply(message) {
    let response = '';
    
    if (message.includes('pending')) {
        response = 'You can view pending applications in the Applications section.';
    } else if (message.includes('Help')) {
        response = 'I can help you with applications, student management, and more. What do you need?';
    } else {
        response = 'How else can I assist you?';
    }
    
    setTimeout(() => {
        addBotMessage(response);
    }, 1000);
}

// Utility Functions
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
        info: 'bg-blue-500'
    };
    
    toast.className = `fixed bottom-4 right-4 ${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg z-50 transform transition-all duration-300 translate-y-20 opacity-0`;
    toast.textContent = message;
    toast.setAttribute('role', 'alert');
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.classList.remove('translate-y-20', 'opacity-0');
    }, 100);
    
    setTimeout(() => {
        toast.classList.add('translate-y-20', 'opacity-0');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}