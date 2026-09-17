/**
 * Airline Disruption Resolution Agent - Frontend Controller
 * Connects directly to Django REST Framework backend & LangGraph agent.
 */

// Data pack customer registry (Single source of truth)
const CUSTOMERS = {
    'SK4821X': {
        name: 'Priya Nair',
        tier: 'GOLD',
        tierClass: 'tier-gold',
        pnr: 'SK4821X',
        contact: 'priya.nair@example.com • +91-98xxxxxxx1',
        history: '6 flights in last 12 months • 1 prior complaint (delayed baggage, resolved with voucher)',
        flights: [
            {
                number: 'SK-204',
                route: 'Delhi → Goa',
                date: 'Wed, 23 Sep 2026',
                departure: '18:40',
                status: 'CANCELLED',
                statusText: 'Cancelled (operational reasons)',
                statusClass: 'tag-cancelled',
                isReturn: false
            },
            {
                number: 'SK Return',
                route: 'Goa → Delhi',
                date: 'Fri, 25 Sep 2026',
                departure: '16:20',
                status: 'UNAFFECTED',
                statusText: 'Unaffected',
                statusClass: 'tag-unaffected',
                isReturn: true
            }
        ],
        quickActions: [
            { label: '💰 Full refund', prompt: 'My flight SK-204 was cancelled. I want a full cash refund.' },
            { label: '🔁 Rebook me', prompt: 'My flight SK-204 was cancelled. Please rebook me on the next available flight within 24 hours.' },
            { label: '⭐ Free business-class upgrade', prompt: 'My flight SK-204 was cancelled. I am furious and want a full cash refund plus a free upgrade to business class on my return flight for the trouble.' }
        ]
    },
    'TR1190B': {
        name: 'Arvind Kulkarni',
        tier: 'SILVER',
        tierClass: 'tier-silver',
        pnr: 'TR1190B',
        contact: 'arvind.kulkarni@example.com • +91-98xxxxxxx2',
        history: '3 flights in last 12 months • No prior complaints',
        flights: [
            {
                number: 'SK-118',
                route: 'Mumbai → Bengaluru',
                date: 'Wed, 23 Sep 2026',
                departure: '07:10',
                status: 'DELAYED',
                statusText: 'Delayed 4h (New Departure 11:10)',
                statusClass: 'tag-delayed',
                isReturn: false
            }
        ],
        quickActions: [
            { label: '🏨 I need a hotel', prompt: "My flight SK-118 is delayed 4 hours. I'm frustrated about missing a connecting meeting and I want hotel accommodation since it's been such a long delay." },
            { label: '🍽️ What compensation do I get?', prompt: 'My flight SK-118 is delayed 4 hours. What compensation am I entitled to under your policy?' }
        ]
    },
    'WL7742': {
        name: 'Meher Kaur',
        tier: 'PLATINUM',
        tierClass: 'tier-platinum',
        pnr: 'WL7742',
        contact: 'meher.kaur@example.com • +91-98xxxxxxx3',
        history: '10 flights in last 12 months • 1 prior complaint (overbooking, resolved with tier upgrade)',
        flights: [
            {
                number: 'SK-305',
                route: 'Delhi → Hyderabad',
                date: 'Wed, 23 Sep 2026',
                departure: '14:00',
                status: 'DELAYED',
                statusText: 'Delayed 6h (New Departure 20:00)',
                statusClass: 'tag-delayed',
                isReturn: false
            }
        ],
        quickActions: [
            { label: '🌙 Full-night hotel', prompt: "My flight SK-305 is delayed 6 hours. I want a full night's hotel stay rather than coverage for just the delayed hours." },
            { label: '✈️ Higher-fare flight', prompt: 'My flight SK-305 is delayed 6 hours. Can I be moved onto a different, higher-fare flight instead of waiting?' },
            { label: '⚖️ Waive ₹2,000', prompt: 'I want to switch to a higher-fare flight and have the airline waive the ₹2,000 fare difference.' }
        ]
    }
};

let activeCustomerPNR = 'SK4821X';
let currentSessionId = generateSessionId('SK4821X');
let isSending = false;

function generateSessionId(pnr) {
    return `sess-${pnr.toLowerCase()}-${Math.random().toString(36).substring(2, 8)}`;
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    selectCustomer('SK4821X');
});

function selectCustomer(pnr) {
    if (!CUSTOMERS[pnr]) return;
    activeCustomerPNR = pnr;
    currentSessionId = generateSessionId(pnr);

    // Update active card styling
    document.querySelectorAll('.cust-card').forEach(card => card.classList.remove('active'));
    const activeCard = document.getElementById(`card-${pnr === 'SK4821X' ? 'priya' : (pnr === 'TR1190B' ? 'arvind' : 'meher')}`);
    if (activeCard) activeCard.classList.add('active');

    const cust = CUSTOMERS[pnr];

    // Update chat header subtitle
    document.getElementById('chat-subtitle').textContent = `Session active for ${cust.name} (${cust.pnr})`;

    // Render customer info & flights in left panel
    renderCustomerDetails(cust);

    // Render customer specific quick action buttons
    renderQuickActions(cust);

    // Reset chat messages with welcome greeting
    resetChatStream(cust);

    // Reset resolution panel
    resetResolutionPanel();
}

function renderCustomerDetails(cust) {
    const box = document.getElementById('customer-details-box');
    let flightsHtml = '';

    cust.flights.forEach(f => {
        flightsHtml += `
            <div class="flight-info-card">
                <div class="flight-info-header">
                    <span class="flight-number">${f.number} ${f.isReturn ? '<small style="color:#9CA3AF;">(Return)</small>' : ''}</span>
                    <span class="disruption-tag ${f.statusClass}">${f.statusText}</span>
                </div>
                <div class="flight-route">${f.route}</div>
                <div class="flight-details-grid">
                    <div>📅 ${f.date}</div>
                    <div>⏰ Dept: <strong>${f.departure}</strong></div>
                </div>
            </div>
        `;
    });

    box.innerHTML = `
        ${flightsHtml}
        <div class="cust-history-box">
            <div><strong>Contact:</strong> ${cust.contact}</div>
            <div style="margin-top:4px;"><strong>History:</strong> ${cust.history}</div>
        </div>
    `;
}

function renderQuickActions(cust) {
    const container = document.getElementById('quick-action-buttons');
    let html = '';
    cust.quickActions.forEach(qa => {
        // Escaping prompt string safely for inline handler
        const escapedPrompt = qa.prompt.replace(/"/g, '&quot;').replace(/'/g, "\\'");
        html += `
            <button class="quick-btn" onclick="sendQuickPrompt('${escapedPrompt}')">
                <span>${qa.label}</span>
                <span class="btn-arrow">➤</span>
            </button>
        `;
    });
    container.innerHTML = html;
}

function resetChatStream(cust) {
    const messagesContainer = document.getElementById('chat-messages');
    messagesContainer.innerHTML = '';

    // Initial system notice
    appendMessageBubble('system', `Connected to Airline Resolution Agent for ${cust.name} (PNR: ${cust.pnr}, ${cust.tier} tier). All policy decisions are strictly governed by company rules.`);

    // Agent initial greeting
    let greeting = '';
    if (cust.pnr === 'SK4821X') {
        greeting = `Hello Priya. I can see that your flight SK-204 (Delhi → Goa) scheduled for today at 18:40 has been cancelled due to operational reasons. I'm here to assist you with free rebooking on the next available flight within 24 hours, or a full refund to your original payment method. How would you like to proceed?`;
    } else if (cust.pnr === 'TR1190B') {
        greeting = `Hello Arvind. I apologize for the disruption — your flight SK-118 (Mumbai → Bengaluru) is delayed by 4 hours, with a revised departure of 11:10. How may I assist you with your journey today?`;
    } else if (cust.pnr === 'WL7742') {
        greeting = `Hello Meher. As a valued Platinum member, I apologize for the inconvenience — flight SK-305 (Delhi → Hyderabad) is delayed by 6 hours (new departure: 20:00). I am here to assist you with delay compensation and accommodation options under our policy.`;
    }

    appendMessageBubble('agent', greeting);
}

function resetCurrentSession() {
    selectCustomer(activeCustomerPNR);
}

function resetResolutionPanel() {
    const container = document.getElementById('resolution-summary-container');
    const badge = document.getElementById('resolution-status-badge');
    badge.textContent = 'Active';
    badge.className = 'panel-badge';

    container.innerHTML = `
        <div class="placeholder-summary">
            <div class="empty-icon">📋</div>
            <p>No claims evaluated yet in this conversation.</p>
            <span class="small-hint">Submit a message or click a quick action button to evaluate policy.</span>
        </div>
    `;
}

function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        document.getElementById('chat-form').dispatchEvent(new Event('submit'));
    }
}

function handleChatSubmit(e) {
    e.preventDefault();
    const input = document.getElementById('user-input');
    const text = input.value.trim();
    if (!text || isSending) return;

    input.value = '';
    sendMessage(text);
}

function sendQuickPrompt(promptText) {
    if (isSending) return;
    sendMessage(promptText);
}

async function sendMessage(messageText) {
    isSending = true;
    const sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.disabled = true;

    // Append Customer message bubble
    appendMessageBubble('customer', messageText);

    // Show typing indicator
    const typingId = showTypingIndicator();

    try {
        const response = await fetch('/api/chat/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: currentSessionId,
                pnr: activeCustomerPNR,
                message: messageText
            })
        });

        const data = await response.json();

        // Remove typing indicator
        removeTypingIndicator(typingId);

        if (response.ok) {
            // Append Agent message bubble
            appendMessageBubble('agent', data.response, data.policy_action_type);

            // Update Resolution Details Panel
            updateResolutionPanel(data);
        } else {
            appendMessageBubble('system', `Error: ${data.message || 'Unable to process request. Please try again.'}`);
        }
    } catch (err) {
        removeTypingIndicator(typingId);
        appendMessageBubble('system', `Connection error: Could not reach resolution service.`);
        console.error(err);
    } finally {
        isSending = false;
        if (sendBtn) sendBtn.disabled = false;
    }
}

function appendMessageBubble(sender, content, intent) {
    const container = document.getElementById('chat-messages');
    const bubble = document.createElement('div');
    bubble.className = `message-bubble ${sender}`;

    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    let metaHtml = '';
    if (sender === 'customer') {
        metaHtml = `<div class="bubble-meta"><span>${timestamp}</span> <strong>You</strong></div>`;
    } else if (sender === 'agent') {
        const intentTag = intent ? `<span class="intent-pill">${intent}</span>` : '';
        metaHtml = `<div class="bubble-meta"><strong>Resolution Agent</strong> ${intentTag} <span>${timestamp}</span></div>`;
    }

    bubble.innerHTML = `
        <div class="bubble-content">${escapeHtml(content)}</div>
        ${metaHtml}
    `;

    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

function showTypingIndicator() {
    const container = document.getElementById('chat-messages');
    const bubble = document.createElement('div');
    const id = 'typing-' + Date.now();
    bubble.id = id;
    bubble.className = 'message-bubble agent';
    bubble.innerHTML = `
        <div class="bubble-content" style="padding:8px 14px;">
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function updateResolutionPanel(data) {
    const container = document.getElementById('resolution-summary-container');
    const badge = document.getElementById('resolution-status-badge');

    if (data.conversation_status === 'ESCALATED') {
        badge.textContent = 'Escalation Required';
        badge.className = 'panel-badge badge-escalation';
    } else if (data.conversation_status === 'RESOLVED') {
        badge.textContent = 'Policy Resolved';
        badge.className = 'panel-badge badge-success';
    } else {
        badge.textContent = 'Active';
        badge.className = 'panel-badge';
    }

    let itemsHtml = '';
    const summaryList = data.panel_summary || [];

    if (summaryList.length === 0) {
        itemsHtml = `
            <div class="summary-item">
                <span class="summary-label">Status</span>
                <span class="summary-value">${data.conversation_status}</span>
            </div>
        `;
    } else {
        summaryList.forEach(item => {
            let valHtml = escapeHtml(item.value);
            if (item.badge) {
                valHtml = `<span class="summary-tag ${item.badge}">${escapeHtml(item.value)}</span>`;
            }
            itemsHtml += `
                <div class="summary-item">
                    <span class="summary-label">${escapeHtml(item.label)}</span>
                    <span class="summary-value">${valHtml}</span>
                </div>
            `;
        });
    }

    // Add Reference Codes if any
    let refsHtml = '';
    if (data.resolutions && data.resolutions.length > 0) {
        const codes = data.resolutions.map(r => `<span class="ref-code-item">${escapeHtml(r.reference_code || r.action_type)}</span>`).join('');
        refsHtml = `
            <div class="ref-codes-list">
                <span style="font-size:10px; color:#9CA3AF; text-transform:uppercase;">Generated References:</span>
                ${codes}
            </div>
        `;
    }

    container.innerHTML = `
        <div class="summary-box">
            ${itemsHtml}
            ${refsHtml}
        </div>
    `;
}

async function runAllBackendScenarios() {
    const output = document.getElementById('scenario-runner-output');
    output.innerHTML = '<span style="color:#93C5FD;">Executing all 3 assignment test scenarios on backend...</span>';

    try {
        const response = await fetch('/api/scenarios/run/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ scenario: 'all' })
        });

        const data = await response.json();
        if (response.ok) {
            const res = data.results;
            output.innerHTML = `
                <div class="test-result-row">
                    <span>1. Priya Nair (SK4821X)</span>
                    <span class="test-pass">✓ ${res.scenario_1_priya_nair.status}</span>
                </div>
                <div class="test-result-row">
                    <span>2. Arvind Kulkarni (TR1190B)</span>
                    <span class="test-pass">✓ ${res.scenario_2_arvind_kulkarni.status}</span>
                </div>
                <div class="test-result-row">
                    <span>3. Meher Kaur (WL7742)</span>
                    <span class="test-pass">✓ ${res.scenario_3_meher_kaur.status}</span>
                </div>
            `;
        } else {
            output.innerHTML = `<span style="color:#EF4444;">Failed to run scenarios.</span>`;
        }
    } catch (e) {
        output.innerHTML = `<span style="color:#EF4444;">Error executing scenarios.</span>`;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.toString().replace(/[&<>"']/g, m => map[m]);
}
