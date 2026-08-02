// Telegram WebApp Initialization
const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

if (tg) {
    tg.ready();
    tg.expand();
    // Adapt header background to telegram colors if possible
    if (tg.setHeaderColor) {
        tg.setHeaderColor('#0a0e17');
    }
}

// State
let currentCategory = 'rent_paphos';
let currentMaxPrice = 0; // 0 = all
let currentSearch = '';
let villasData = [];
let favorites = JSON.parse(localStorage.getItem('paphos_favorites') || '[]');

// Realistic Paphos fallback dataset (when opening offline or without backend)
const DEMO_VILLAS = [
    {
        id: 101,
        category: 'rent_paphos',
        price: 4500,
        channel: 'nedvizhka_Ciprus',
        created_at: '2026-08-01 12:30',
        url: 'https://t.me/nedvizhka_Ciprus/101',
        text: '📍 Пафос, Тала (Tala)\n\nСдаётся роскошная 4-спальная вилла с панорамным видом на море и собственным переливным бассейном.\n\n• Площадь: 280 м²\n• 4 спальни со своими санузлами\n• Современная техника Miele, система умный дом\n• Крытый паркинг на 2 авто\n• Садовник и чистка бассейна включены в стоимость!'
    },
    {
        id: 102,
        category: 'rent_paphos',
        price: 2800,
        channel: 'nedvizhka_Ciprus',
        created_at: '2026-08-01 11:15',
        url: 'https://t.me/nedvizhka_Ciprus/102',
        text: '📍 Пафос, Корал Бэй (Coral Bay)\n\nАренда современной 3-спальной виллы в 300 метрах от песчаного пляжа Корал Бэй.\n\n• Полный комплект мебели и кондиционеры во всех комнатах\n• Большое патио и зона барбекю\n• Закрытый тихий комплекс\n• Готова к немедленному заселению'
    },
    {
        id: 103,
        category: 'rent_paphos',
        price: 1800,
        channel: 'nedvizhka_Ciprus',
        created_at: '2026-08-01 09:40',
        url: 'https://t.me/nedvizhka_Ciprus/103',
        text: '📍 Пафос, Хлорака (Chloraka)\n\nУютный 3-спальный дом в долгосрочную аренду с приватным двориком.\n\n• 3 спальни, 2 санузла\n• Новая кухня, свежий косметический ремонт\n• Близость к английским школам и супермаркетам'
    },
    {
        id: 104,
        category: 'rent_paphos',
        price: 3500,
        channel: 'nedvizhka_Ciprus',
        created_at: '2026-07-31 18:20',
        url: 'https://t.me/nedvizhka_Ciprus/104',
        text: '📍 Пафос, Пейя (Peyia)\n\nПанорамная вилла в аренду с видом на залив.\n\n• 4 спальни, бассейн с подогревом\n• Камин в гостиной, большая веранда\n• Ухоженный зеленый сад'
    },
    {
        id: 201,
        category: 'sale_villa',
        price: 1850000,
        channel: 'nedvizhka_Ciprus',
        created_at: '2026-08-01 10:00',
        url: 'https://t.me/nedvizhka_Ciprus/201',
        text: '🏡 Пафос, Цада (Tsada / Minthis)\n\nЭксклюзивная вилла на продажу в элитном гольф-курорте.\n\n• Площадь дома: 380 м², участок: 1200 м²\n• Архитектурный проект премиум-класса, панорамное остекление\n• Индивидуальный бассейн, SPA-зона\n• Титул собственника в наличии (Title Deeds)'
    },
    {
        id: 202,
        category: 'sale_villa',
        price: 650000,
        channel: 'nedvizhka_Ciprus',
        created_at: '2026-07-31 14:10',
        url: 'https://t.me/nedvizhka_Ciprus/202',
        text: '🏡 Пафос, Кония (Konia)\n\nПродажа современной 4-спальной виллы в престижном пригороде Пафоса.\n\n• Энергоэффективность класса А\n• Теплые полы, солнечные панели\n• Удобный выезд на трассу и близость к школам'
    }
];

// DOM Elements
const villasGrid = document.getElementById('villasGrid');
const loadingState = document.getElementById('loadingState');
const emptyState = document.getElementById('emptyState');
const budgetPillsContainer = document.getElementById('budgetPills');
const searchInput = document.getElementById('searchInput');
const clearSearchBtn = document.getElementById('clearSearchBtn');
const favCountBadge = document.getElementById('favCountBadge');
const resetFiltersBtn = document.getElementById('resetFiltersBtn');

// Modal Elements
const modalOverlay = document.getElementById('villaModalOverlay');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const modalContent = document.getElementById('modalContent');
const toast = document.getElementById('toast');

// User details display
function initUserInfo() {
    const userNameEl = document.getElementById('userName');
    const userAvatarEl = document.getElementById('userAvatar');
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
        const u = tg.initDataUnsafe.user;
        userNameEl.textContent = u.first_name || 'Пользователь';
    }
}

// Update budget pills based on current tab
function updateBudgetPills() {
    budgetPillsContainer.innerHTML = '';
    const rentPills = [
        { label: 'Все цены', val: 0 },
        { label: 'До 1 500 €', val: 1500 },
        { label: 'До 3 000 €', val: 3000 },
        { label: 'До 5 000 €', val: 5000 }
    ];
    const salePills = [
        { label: 'Все цены', val: 0 },
        { label: 'До 500k €', val: 500000 },
        { label: 'До 1M €', val: 1000000 },
        { label: 'Люкс 1M+', val: -1 }
    ];

    const pills = currentCategory === 'sale_villa' ? salePills : rentPills;
    pills.forEach((p, idx) => {
        const btn = document.createElement('button');
        btn.className = `pill-btn ${p.val === currentMaxPrice ? 'active' : ''}`;
        btn.textContent = p.label;
        btn.addEventListener('click', () => {
            currentMaxPrice = p.val;
            document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            hapticFeedback('light');
            renderVillas();
        });
        budgetPillsContainer.appendChild(btn);
    });
}

// Fetch villas from API or fallback
async function fetchVillas() {
    loadingState.classList.remove('hidden');
    villasGrid.innerHTML = '';
    emptyState.classList.add('hidden');

    try {
        const response = await fetch(`/api/villas?category=${currentCategory}&limit=50`);
        if (response.ok) {
            const data = await response.json();
            villasData = data;
        } else {
            throw new Error('API not available');
        }
    } catch (e) {
        // Fallback to offline demo data
        villasData = DEMO_VILLAS;
    } finally {
        loadingState.classList.add('hidden');
        renderVillas();
        updateFavBadge();
    }
}

// Render cards
function renderVillas() {
    villasGrid.innerHTML = '';
    let filtered = villasData;

    // Filter by Category or Favorites
    if (currentCategory === 'favorites') {
        filtered = filtered.filter(v => favorites.includes(v.id));
    } else {
        filtered = filtered.filter(v => v.category === currentCategory);
    }

    // Filter by Budget
    if (currentMaxPrice > 0) {
        filtered = filtered.filter(v => v.price <= currentMaxPrice);
    } else if (currentMaxPrice === -1) {
        filtered = filtered.filter(v => v.price >= 1000000);
    }

    // Filter by Search
    if (currentSearch.trim() !== '') {
        const q = currentSearch.toLowerCase();
        filtered = filtered.filter(v => (v.text || '').toLowerCase().includes(q));
    }

    if (filtered.length === 0) {
        emptyState.classList.remove('hidden');
        return;
    }
    emptyState.classList.add('hidden');

    filtered.forEach(v => {
        const isFav = favorites.includes(v.id);
        const card = document.createElement('div');
        card.className = 'villa-card';

        const priceFormatted = v.price.toLocaleString('ru-RU') + ' €';
        const isRent = v.category === 'rent_paphos';
        const chipText = isRent ? 'Аренда' : 'Продажа';
        const chipClass = isRent ? 'chip-rent' : 'chip-sale';

        card.innerHTML = `
            <div class="card-header">
                <div class="price-tag">${priceFormatted}</div>
                <span class="category-chip ${chipClass}">${chipText}</span>
            </div>
            <div class="card-snippet">${v.text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
            <div class="card-footer">
                <span class="source-info">📍 @${v.channel} • ${v.created_at || ''}</span>
                <div class="card-actions">
                    <button class="action-btn btn-fav ${isFav ? 'active' : ''}" data-id="${v.id}" title="В Избранное">❤️</button>
                    <a href="${v.url}" target="_blank" class="action-btn" title="Открыть в Telegram">🔗</a>
                </div>
            </div>
        `;

        // Click card to open detail modal
        card.addEventListener('click', (e) => {
            if (e.target.closest('.action-btn')) return;
            openModal(v);
        });

        // Toggle favorite
        const favBtn = card.querySelector('.btn-fav');
        favBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleFavorite(v.id, favBtn);
        });

        villasGrid.appendChild(card);
    });
}

// Favorite bookmark logic
function toggleFavorite(id, btnEl) {
    const idx = favorites.indexOf(id);
    if (idx === -1) {
        favorites.push(id);
        btnEl.classList.add('active');
        showToast('❤️ Добавлено в Избранное');
        hapticFeedback('medium');
    } else {
        favorites.splice(idx, 1);
        btnEl.classList.remove('active');
        showToast('Удалено из Избранного');
        hapticFeedback('light');
        if (currentCategory === 'favorites') {
            renderVillas();
        }
    }
    localStorage.setItem('paphos_favorites', JSON.stringify(favorites));
    updateFavBadge();
}

function updateFavBadge() {
    const count = favorites.length;
    favCountBadge.textContent = count;
    favCountBadge.setAttribute('data-count', count);
}

// Modal Detail View
function openModal(v) {
    hapticFeedback('light');
    const priceFormatted = v.price.toLocaleString('ru-RU') + ' €';
    const isRent = v.category === 'rent_paphos';
    const chipText = isRent ? 'Аренда в Пафосе' : 'Продажа виллы в Пафосе';

    modalContent.innerHTML = `
        <div class="modal-price">${priceFormatted}</div>
        <div class="modal-source">📍 Канал: @${v.channel} • ${v.created_at || 'Недавно'} • ${chipText}</div>
        <div class="modal-text">${v.text}</div>
        <a href="${v.url}" target="_blank" class="modal-btn">👉 Открыть оригинал в Telegram</a>
    `;

    modalOverlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    modalOverlay.classList.add('hidden');
    document.body.style.overflow = '';
}

modalCloseBtn.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', (e) => {
    if (e.target === modalOverlay) closeModal();
});

// Search bar event
searchInput.addEventListener('input', (e) => {
    currentSearch = e.target.value;
    clearSearchBtn.classList.toggle('visible', currentSearch.length > 0);
    renderVillas();
});

clearSearchBtn.addEventListener('click', () => {
    searchInput.value = '';
    currentSearch = '';
    clearSearchBtn.classList.remove('visible');
    renderVillas();
});

resetFiltersBtn.addEventListener('click', () => {
    currentMaxPrice = 0;
    currentSearch = '';
    searchInput.value = '';
    clearSearchBtn.classList.remove('visible');
    updateBudgetPills();
    renderVillas();
});

// Category switching
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentCategory = btn.getAttribute('data-category');
        currentMaxPrice = 0;
        hapticFeedback('medium');
        updateBudgetPills();
        renderVillas();
    });
});

// Haptic feedback helper
function hapticFeedback(style = 'light') {
    if (tg && tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred(style);
    }
}

// Toast helper
let toastTimeout;
function showToast(msg) {
    clearTimeout(toastTimeout);
    toast.textContent = msg;
    toast.classList.remove('hidden');
    toastTimeout = setTimeout(() => {
        toast.classList.add('hidden');
    }, 2500);
}

// Init
initUserInfo();
updateBudgetPills();
fetchVillas();
