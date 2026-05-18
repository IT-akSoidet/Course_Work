const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}
const devTgId = readDevTelegramIdFromLocation();

function readInitDataFromLocation() {
  const sources = [];
  const rawHash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (rawHash) {
    sources.push(new URLSearchParams(rawHash));
  }
  if (window.location.search) {
    sources.push(new URLSearchParams(window.location.search));
  }

  for (const params of sources) {
    const raw =
      params.get("tgWebAppData") ||
      params.get("tgWebAppInitData") ||
      params.get("initData");
    if (!raw) {
      continue;
    }
    try {
      return decodeURIComponent(raw);
    } catch {
      return raw;
    }
  }
  return "";
}

function readDevTelegramIdFromLocation() {
  const fromSearch = new URLSearchParams(window.location.search).get("dev_tg_id");
  if (fromSearch && /^\d+$/.test(fromSearch)) {
    return Number.parseInt(fromSearch, 10);
  }
  const rawHash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  const fromHash = new URLSearchParams(rawHash).get("dev_tg_id");
  if (fromHash && /^\d+$/.test(fromHash)) {
    return Number.parseInt(fromHash, 10);
  }
  return null;
}

const state = {
  initData: tg?.initData?.trim() || readInitDataFromLocation(),
  fallbackUser:
    tg?.initDataUnsafe?.user ||
    (devTgId
      ? {
          id: devTgId,
          first_name: "Dev",
          last_name: "User",
        }
      : null),
  startsAt: null,
  endsAt: null,
  roleId: null,
};

const els = {
  tabs: document.querySelectorAll(".tab"),
  panels: document.querySelectorAll(".tab-panel"),
  alerts: document.getElementById("alerts"),
  userBadge: document.getElementById("user-badge"),
  adminTabBtn: document.getElementById("admin-tab-btn"),
  searchForm: document.getElementById("search-form"),
  searchStart: document.getElementById("search-start"),
  searchEnd: document.getElementById("search-end"),
  searchCapacity: document.getElementById("search-capacity"),
  roomsResults: document.getElementById("rooms-results"),
  bookingsList: document.getElementById("bookings-list"),
  refreshBookings: document.getElementById("refresh-bookings"),
  adminList: document.getElementById("admin-list"),
  refreshAdmin: document.getElementById("refresh-admin"),
  roomCardTemplate: document.getElementById("room-card-template"),
};

function showAlert(message, tone = "success") {
  const div = document.createElement("div");
  div.className = `alert ${tone === "error" ? "alert-error" : "alert-success"}`;
  div.textContent = message;
  els.alerts.innerHTML = "";
  els.alerts.append(div);
  setTimeout(() => {
    if (els.alerts.contains(div)) {
      els.alerts.removeChild(div);
    }
  }, 5000);
}

function toIsoLocal(value) {
  if (!value) {
    return "";
  }
  const dt = new Date(value);
  dt.setMinutes(dt.getMinutes() - dt.getTimezoneOffset());
  return dt.toISOString().slice(0, 16);
}

function formatDateTime(value) {
  const dt = new Date(value);
  return dt.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function api(path, options = {}) {
  const fallbackId = state.fallbackUser?.id;
  if (!state.initData && !fallbackId) {
    throw new Error("Откройте интерфейс внутри Telegram WebApp.");
  }
  const extraHeaders = {};
  if (fallbackId && !state.initData) {
    extraHeaders["X-Telegram-Fallback-Id"] = String(fallbackId);
    if (state.fallbackUser?.first_name || state.fallbackUser?.last_name) {
      const fullName = [state.fallbackUser.first_name, state.fallbackUser.last_name]
        .filter(Boolean)
        .join(" ");
      extraHeaders["X-Telegram-Fallback-Name"] = fullName;
    }
  }
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": state.initData,
      ...extraHeaders,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    let errorDetail = "Ошибка запроса";
    try {
      const payload = await response.json();
      errorDetail = payload.detail || errorDetail;
    } catch {
      errorDetail = await response.text();
    }
    throw new Error(errorDetail);
  }
  return response.json();
}

function setActiveTab(tabName) {
  els.tabs.forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === tabName);
  });
  els.panels.forEach((panel) => {
    panel.hidden = panel.dataset.panel !== tabName;
  });
}

function renderRooms(rooms) {
  els.roomsResults.innerHTML = "";
  if (!rooms.length) {
    els.roomsResults.textContent = "Свободных аудиторий не найдено.";
    return;
  }
  rooms.forEach((room) => {
    const node = els.roomCardTemplate.content.firstElementChild.cloneNode(true);
    node.querySelector(".item-title").textContent = `Ауд. ${room.name} (ID ${room.id})`;
    node.querySelector(".room-building").textContent = `${room.building_name}, ${room.building_address}`;
    node.querySelector(".room-capacity").textContent = `Вместимость: ${room.capacity}`;
    const purposeInput = node.querySelector(".purpose-input");
    node.querySelector(".room-book-btn").addEventListener("click", async () => {
      if (!state.startsAt || !state.endsAt) {
        showAlert("Сначала задайте интервал поиска.", "error");
        return;
      }
      try {
        const booking = await api("/webapp/api/bookings", {
          method: "POST",
          body: JSON.stringify({
            room_id: room.id,
            starts_at: state.startsAt,
            ends_at: state.endsAt,
            purpose: purposeInput.value.trim(),
          }),
        });
        showAlert(`Бронь #${booking.booking_id} создана: ${booking.status_label}`);
        await loadMyBookings();
      } catch (error) {
        showAlert(error.message, "error");
      }
    });
    els.roomsResults.append(node);
  });
}

function renderMyBookings(bookings) {
  els.bookingsList.innerHTML = "";
  if (!bookings.length) {
    els.bookingsList.textContent = "У вас нет активных бронирований.";
    return;
  }

  bookings.forEach((booking) => {
    const card = document.createElement("article");
    card.className = "item-card";
    card.innerHTML = `
      <h3 class="item-title">Бронь #${booking.booking_id} · ауд. ${booking.room_id}</h3>
      <p class="muted">С ${formatDateTime(booking.starts_at)} до ${formatDateTime(booking.ends_at)}</p>
      <p class="muted">Статус: ${booking.status_label}</p>
      <p class="muted">${booking.purpose ? `Цель: ${booking.purpose}` : "Цель не указана"}</p>
      <div class="item-actions"></div>
    `;
    const actions = card.querySelector(".item-actions");
    const cancelBtn = document.createElement("button");
    cancelBtn.className = "btn btn-danger";
    cancelBtn.type = "button";
    cancelBtn.textContent = "Отменить";
    cancelBtn.addEventListener("click", async () => {
      try {
        await api(`/webapp/api/bookings/${booking.booking_id}/cancel`, { method: "POST" });
        showAlert(`Бронь #${booking.booking_id} отменена.`);
        await loadMyBookings();
      } catch (error) {
        showAlert(error.message, "error");
      }
    });
    actions.append(cancelBtn);
    els.bookingsList.append(card);
  });
}

function renderAdminQueue(items) {
  els.adminList.innerHTML = "";
  if (!items.length) {
    els.adminList.textContent = "Очередь модерации пуста.";
    return;
  }
  items.forEach((booking) => {
    const card = document.createElement("article");
    card.className = "item-card";
    card.innerHTML = `
      <h3 class="item-title">Заявка #${booking.booking_id} · ауд. ${booking.room_id}</h3>
      <p class="muted">С ${formatDateTime(booking.starts_at)} до ${formatDateTime(booking.ends_at)}</p>
      <p class="muted">${booking.purpose ? `Цель: ${booking.purpose}` : "Цель не указана"}</p>
      <div class="item-actions"></div>
    `;
    const actions = card.querySelector(".item-actions");
    const approveBtn = document.createElement("button");
    approveBtn.className = "btn btn-primary";
    approveBtn.type = "button";
    approveBtn.textContent = "Подтвердить";
    approveBtn.addEventListener("click", async () => {
      try {
        await api(`/webapp/api/admin/queue/${booking.booking_id}/approve`, { method: "POST" });
        showAlert(`Заявка #${booking.booking_id} подтверждена.`);
        await loadAdminQueue();
      } catch (error) {
        showAlert(error.message, "error");
      }
    });
    const rejectBtn = document.createElement("button");
    rejectBtn.className = "btn btn-danger";
    rejectBtn.type = "button";
    rejectBtn.textContent = "Отклонить";
    rejectBtn.addEventListener("click", async () => {
      try {
        await api(`/webapp/api/admin/queue/${booking.booking_id}/reject`, { method: "POST" });
        showAlert(`Заявка #${booking.booking_id} отклонена.`);
        await loadAdminQueue();
      } catch (error) {
        showAlert(error.message, "error");
      }
    });
    actions.append(approveBtn, rejectBtn);
    els.adminList.append(card);
  });
}

async function loadMyBookings() {
  const payload = await api("/webapp/api/bookings/mine");
  renderMyBookings(payload.bookings || []);
}

async function loadAdminQueue() {
  if (state.roleId !== 3) {
    return;
  }
  const payload = await api("/webapp/api/admin/queue");
  renderAdminQueue(payload.pending || []);
}

async function bootstrap() {
  try {
    const payload = await api("/webapp/api/bootstrap");
    state.roleId = payload.user.role_id;
    els.userBadge.textContent = `${payload.user.full_name} · ID ${payload.user.id}`;
    if (state.roleId === 3) {
      els.adminTabBtn.hidden = false;
    }
    await loadMyBookings();
  } catch (error) {
    showAlert(error.message, "error");
    els.userBadge.textContent = "Не удалось выполнить авторизацию.";
  }
}

els.tabs.forEach((btn) => {
  btn.addEventListener("click", async () => {
    const tab = btn.dataset.tab;
    setActiveTab(tab);
    if (tab === "bookings") {
      await loadMyBookings();
    } else if (tab === "admin") {
      await loadAdminQueue();
    }
  });
});

els.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const startsRaw = els.searchStart.value;
  const endsRaw = els.searchEnd.value;
  const minCapacity = Number.parseInt(els.searchCapacity.value, 10);
  if (!startsRaw || !endsRaw || Number.isNaN(minCapacity) || minCapacity < 1) {
    showAlert("Заполните параметры поиска корректно.", "error");
    return;
  }

  state.startsAt = new Date(startsRaw).toISOString();
  state.endsAt = new Date(endsRaw).toISOString();
  if (state.startsAt >= state.endsAt) {
    showAlert("Начало должно быть раньше окончания.", "error");
    return;
  }

  try {
    const payload = await api(
      `/webapp/api/rooms/available?starts_at=${encodeURIComponent(state.startsAt)}&ends_at=${encodeURIComponent(state.endsAt)}&min_capacity=${minCapacity}`
    );
    renderRooms(payload.rooms || []);
  } catch (error) {
    showAlert(error.message, "error");
  }
});

els.refreshBookings.addEventListener("click", async () => {
  try {
    await loadMyBookings();
    showAlert("Список бронирований обновлен.");
  } catch (error) {
    showAlert(error.message, "error");
  }
});

els.refreshAdmin.addEventListener("click", async () => {
  try {
    await loadAdminQueue();
    showAlert("Очередь модерации обновлена.");
  } catch (error) {
    showAlert(error.message, "error");
  }
});

const now = new Date();
const end = new Date(now.getTime() + 60 * 60 * 1000);
els.searchStart.value = toIsoLocal(now);
els.searchEnd.value = toIsoLocal(end);

bootstrap();
