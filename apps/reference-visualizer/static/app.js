const API = "/api";
const DEFAULT_ITEM_SIZE = { width: 260, height: 180 };

const elements = {
  boardSelect: document.getElementById("board-select"),
  boardStage: document.getElementById("board-stage"),
  boardViewport: document.getElementById("board-viewport"),
  deleteBoard: document.getElementById("delete-board"),
  emptyBoard: document.getElementById("empty-board"),
  newBoard: document.getElementById("new-board"),
  referenceList: document.getElementById("reference-list"),
  referenceSearch: document.getElementById("reference-search"),
  resetView: document.getElementById("reset-view"),
  saveStatus: document.getElementById("save-status"),
};

const state = {
  activeBoard: null,
  boards: [],
  camera: { x: 40, y: 40, zoom: 1 },
  drag: null,
  newItemIds: new Set(),
  references: [],
  saveQueue: Promise.resolve(),
  saveTimers: new Map(),
  selectedId: null,
};

function artworkUrl(reference) {
  return `${API}/artwork/${encodeURIComponent(reference.filename)}`;
}

function isVideo(reference) {
  return reference.media_type.includes("VIDEO") || /\.(m4v|mov|mp4|webm)$/i.test(reference.filename);
}

function createItemId() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `item-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    // Some successful DELETE responses may not carry JSON.
  }
  if (!response.ok) {
    throw new Error(payload?.detail || `Request failed (${response.status})`);
  }
  return payload;
}

function setStatus(message, isError = false) {
  elements.saveStatus.textContent = message;
  elements.saveStatus.classList.toggle("error", isError);
}

function createMedia(reference, autoplay = false) {
  const media = document.createElement(isVideo(reference) ? "video" : "img");
  media.src = artworkUrl(reference);
  media.draggable = false;
  if (media instanceof HTMLVideoElement) {
    media.muted = true;
    media.loop = true;
    media.autoplay = autoplay;
    media.playsInline = true;
    media.preload = autoplay ? "auto" : "metadata";
  } else {
    media.alt = `${reference.artist} ${reference.track_name}`.trim();
    media.loading = "lazy";
  }
  return media;
}

function renderReferences() {
  const query = elements.referenceSearch.value.trim().toLocaleLowerCase();
  const references = state.references.filter((reference) => {
    const tags = (reference.tags || []).map((tag) => tag.display_name).join(" ");
    return `${reference.artist} ${reference.track_name} ${tags}`.toLocaleLowerCase().includes(query);
  });

  elements.referenceList.replaceChildren();
  if (references.length === 0) {
    const message = document.createElement("div");
    message.className = "library-message";
    message.textContent = state.references.length === 0
      ? "No compiled references are available yet."
      : "No references match this search.";
    elements.referenceList.append(message);
    return;
  }

  for (const reference of references) {
    const card = document.createElement("article");
    card.className = "reference-card";
    card.draggable = true;
    card.title = "Click or drag to add";
    card.append(createMedia(reference));

    const title = document.createElement("div");
    title.className = "reference-card-title";
    title.textContent = [reference.artist, reference.track_name].filter(Boolean).join(" — ");
    card.append(title);

    if (reference.tags?.length) {
      const tags = document.createElement("div");
      tags.className = "reference-card-tags";
      for (const tag of reference.tags.slice(0, 2)) {
        const chip = document.createElement("span");
        chip.className = "mini-tag";
        chip.textContent = tag.display_name;
        tags.append(chip);
      }
      card.append(tags);
    }

    card.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("application/x-reference-id", reference.id);
      event.dataTransfer.effectAllowed = "copy";
    });
    card.addEventListener("click", () => addReferenceAtViewportCenter(reference));
    elements.referenceList.append(card);
  }
}

function renderBoardSelect() {
  elements.boardSelect.replaceChildren();
  if (state.boards.length === 0) {
    const option = new Option("No boards", "");
    elements.boardSelect.add(option);
  } else {
    for (const board of state.boards) {
      elements.boardSelect.add(new Option(board.name, board.id));
    }
    elements.boardSelect.value = state.activeBoard?.id || state.boards[0].id;
  }
  elements.boardSelect.disabled = state.boards.length === 0;
  elements.deleteBoard.disabled = !state.activeBoard;
}

function referenceForItem(item) {
  return state.references.find((reference) => reference.id === item.reference_id);
}

function updateItemElement(item, element) {
  element.style.width = `${item.width}px`;
  element.style.height = `${item.height}px`;
  element.style.transform = `translate(${item.position_x}px, ${item.position_y}px)`;
}

function selectItem(itemId) {
  state.selectedId = itemId;
  for (const element of elements.boardStage.querySelectorAll(".board-item")) {
    element.classList.toggle("selected", element.dataset.itemId === itemId);
  }
}

function removeItem(itemId) {
  if (!state.activeBoard) return;
  state.activeBoard.items = state.activeBoard.items.filter((item) => item.id !== itemId);
  state.newItemIds.delete(itemId);
  if (state.selectedId === itemId) state.selectedId = null;
  renderBoard();
  scheduleSave(state.activeBoard);
}

function fitNewItemToMedia(board, item, media, element) {
  if (!state.newItemIds.has(item.id)) return;
  const naturalWidth = media instanceof HTMLVideoElement ? media.videoWidth : media.naturalWidth;
  const naturalHeight = media instanceof HTMLVideoElement ? media.videoHeight : media.naturalHeight;
  if (!naturalWidth || !naturalHeight) return;

  const centerX = item.position_x + item.width / 2;
  const centerY = item.position_y + item.height / 2;
  const scale = Math.min(360 / naturalWidth, 280 / naturalHeight, 1);
  item.width = Math.max(100, Math.round(naturalWidth * scale));
  item.height = Math.max(80, Math.round(naturalHeight * scale));
  item.position_x = Math.round(centerX - item.width / 2);
  item.position_y = Math.round(centerY - item.height / 2);
  state.newItemIds.delete(item.id);
  updateItemElement(item, element);
  scheduleSave(board);
}

function createBoardItem(item) {
  const board = state.activeBoard;
  const reference = referenceForItem(item);
  const element = document.createElement("article");
  element.className = "board-item";
  element.dataset.itemId = item.id;
  element.classList.toggle("selected", item.id === state.selectedId);
  updateItemElement(item, element);

  if (reference) {
    const media = createMedia(reference, true);
    const loadEvent = media instanceof HTMLVideoElement ? "loadedmetadata" : "load";
    media.addEventListener(
      loadEvent,
      () => fitNewItemToMedia(board, item, media, element),
      { once: true },
    );
    element.append(media);
  } else {
    const missing = document.createElement("div");
    missing.className = "library-message";
    missing.textContent = "Reference unavailable";
    element.append(missing);
  }

  const remove = document.createElement("button");
  remove.className = "remove-item";
  remove.type = "button";
  remove.title = "Remove from board";
  remove.setAttribute("aria-label", "Remove from board");
  remove.textContent = "×";
  remove.addEventListener("pointerdown", (event) => event.stopPropagation());
  remove.addEventListener("click", (event) => {
    event.stopPropagation();
    removeItem(item.id);
  });
  element.append(remove);

  const resize = document.createElement("span");
  resize.className = "resize-handle";
  resize.addEventListener("pointerdown", (event) => beginItemInteraction(event, item, element, "resize"));
  element.append(resize);

  element.addEventListener("pointerdown", (event) => beginItemInteraction(event, item, element, "move"));
  return element;
}

function renderBoard() {
  elements.boardStage.replaceChildren();
  const items = state.activeBoard?.items || [];
  for (const item of items) {
    elements.boardStage.append(createBoardItem(item));
  }
  elements.emptyBoard.classList.toggle("hidden", items.length > 0);
  elements.emptyBoard.querySelector("strong").textContent = state.activeBoard
    ? "Build a mood board"
    : "Create a mood board";
  renderBoardSelect();
}

function renderCamera() {
  const { x, y, zoom } = state.camera;
  elements.boardStage.style.transform = `translate(${x}px, ${y}px) scale(${zoom})`;
}

function resetCamera() {
  state.camera = { x: 40, y: 40, zoom: 1 };
  renderCamera();
}

function viewportPointToBoard(clientX, clientY) {
  const rect = elements.boardViewport.getBoundingClientRect();
  return {
    x: (clientX - rect.left - state.camera.x) / state.camera.zoom,
    y: (clientY - rect.top - state.camera.y) / state.camera.zoom,
  };
}

async function ensureBoard() {
  if (state.activeBoard) return state.activeBoard;
  return createBoard("Mood board");
}

async function addReference(reference, x, y) {
  const board = await ensureBoard();
  const item = {
    id: createItemId(),
    reference_id: reference.id,
    position_x: Math.round(x - DEFAULT_ITEM_SIZE.width / 2),
    position_y: Math.round(y - DEFAULT_ITEM_SIZE.height / 2),
    width: DEFAULT_ITEM_SIZE.width,
    height: DEFAULT_ITEM_SIZE.height,
  };
  board.items.push(item);
  state.newItemIds.add(item.id);
  state.selectedId = item.id;
  renderBoard();
  scheduleSave(board);
}

async function addReferenceAtViewportCenter(reference) {
  const rect = elements.boardViewport.getBoundingClientRect();
  const point = viewportPointToBoard(rect.left + rect.width / 2, rect.top + rect.height / 2);
  await addReference(reference, point.x, point.y);
}

function beginItemInteraction(event, item, element, mode) {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  elements.boardViewport.setPointerCapture(event.pointerId);
  selectItem(item.id);
  state.drag = {
    mode,
    item,
    element,
    pointerId: event.pointerId,
    startClientX: event.clientX,
    startClientY: event.clientY,
    startX: item.position_x,
    startY: item.position_y,
    startWidth: item.width,
    startHeight: item.height,
  };
}

function beginPan(event) {
  if (event.button !== 0 && event.button !== 1) return;
  event.preventDefault();
  elements.boardViewport.setPointerCapture(event.pointerId);
  elements.boardViewport.classList.add("panning");
  selectItem(null);
  state.drag = {
    mode: "pan",
    pointerId: event.pointerId,
    startClientX: event.clientX,
    startClientY: event.clientY,
    startX: state.camera.x,
    startY: state.camera.y,
  };
}

function handlePointerMove(event) {
  const drag = state.drag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const deltaX = event.clientX - drag.startClientX;
  const deltaY = event.clientY - drag.startClientY;

  if (drag.mode === "pan") {
    state.camera.x = drag.startX + deltaX;
    state.camera.y = drag.startY + deltaY;
    renderCamera();
    return;
  }

  if (drag.mode === "move") {
    drag.item.position_x = Math.round(drag.startX + deltaX / state.camera.zoom);
    drag.item.position_y = Math.round(drag.startY + deltaY / state.camera.zoom);
  } else if (drag.mode === "resize") {
    drag.item.width = Math.max(80, Math.round(drag.startWidth + deltaX / state.camera.zoom));
    drag.item.height = Math.max(60, Math.round(drag.startHeight + deltaY / state.camera.zoom));
  }
  updateItemElement(drag.item, drag.element);
}

function finishPointerInteraction(event) {
  if (!state.drag || state.drag.pointerId !== event.pointerId) return;
  const changedBoard = state.drag.mode !== "pan";
  state.drag = null;
  elements.boardViewport.classList.remove("panning");
  if (changedBoard && state.activeBoard) scheduleSave(state.activeBoard);
}

function scheduleSave(board) {
  if (!board) return;
  const existingTimer = state.saveTimers.get(board.id);
  if (existingTimer) window.clearTimeout(existingTimer);
  setStatus("Unsaved changes");
  const timer = window.setTimeout(() => {
    state.saveTimers.delete(board.id);
    persistBoard(board);
  }, 350);
  state.saveTimers.set(board.id, timer);
}

function boardItemsPayload(board) {
  return board.items.map((item) => ({
    id: item.id,
    reference_id: item.reference_id,
    position_x: item.position_x,
    position_y: item.position_y,
    width: item.width,
    height: item.height,
  }));
}

function persistBoard(board) {
  const items = boardItemsPayload(board);
  state.saveQueue = state.saveQueue
    .then(async () => {
      if (state.activeBoard?.id === board.id) setStatus("Saving…");
      await request(`${API}/boards/${encodeURIComponent(board.id)}/items`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      if (state.activeBoard?.id === board.id) setStatus("Saved");
    })
    .catch((error) => {
      console.error(error);
      setStatus("Save failed", true);
    });
}

async function createBoard(name) {
  const board = await request(`${API}/boards`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  state.boards.unshift(board);
  state.activeBoard = board;
  state.selectedId = null;
  resetCamera();
  renderBoard();
  return board;
}

function selectBoard(boardId) {
  state.activeBoard = state.boards.find((board) => board.id === boardId) || null;
  state.selectedId = null;
  resetCamera();
  renderBoard();
}

async function loadApplication() {
  setStatus("Loading…");
  const [references, boards] = await Promise.all([
    request(`${API}/references`),
    request(`${API}/boards`),
  ]);
  state.references = references;
  state.boards = boards;
  state.activeBoard = boards[0] || null;
  renderReferences();
  renderBoard();
  renderCamera();
  setStatus("Ready");
}

elements.referenceSearch.addEventListener("input", renderReferences);
elements.boardSelect.addEventListener("change", () => selectBoard(elements.boardSelect.value));
elements.resetView.addEventListener("click", resetCamera);

elements.newBoard.addEventListener("click", async () => {
  const name = window.prompt("Board name", "Mood board");
  if (!name?.trim()) return;
  try {
    await createBoard(name.trim());
  } catch (error) {
    setStatus(error.message, true);
  }
});

elements.deleteBoard.addEventListener("click", async () => {
  const board = state.activeBoard;
  if (!board || !window.confirm(`Delete “${board.name}”?`)) return;
  try {
    const timer = state.saveTimers.get(board.id);
    if (timer) window.clearTimeout(timer);
    state.saveTimers.delete(board.id);
    await state.saveQueue;
    await request(`${API}/boards/${encodeURIComponent(board.id)}`, { method: "DELETE" });
    state.boards = state.boards.filter((candidate) => candidate.id !== board.id);
    state.activeBoard = state.boards[0] || null;
    state.selectedId = null;
    renderBoard();
    setStatus("Board deleted");
  } catch (error) {
    setStatus(error.message, true);
  }
});

elements.boardViewport.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".board-item")) beginPan(event);
});
elements.boardViewport.addEventListener("pointermove", handlePointerMove);
elements.boardViewport.addEventListener("pointerup", finishPointerInteraction);
elements.boardViewport.addEventListener("pointercancel", finishPointerInteraction);
elements.boardViewport.addEventListener("contextmenu", (event) => event.preventDefault());

elements.boardViewport.addEventListener("wheel", (event) => {
  event.preventDefault();
  const rect = elements.boardViewport.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;
  const worldX = (mouseX - state.camera.x) / state.camera.zoom;
  const worldY = (mouseY - state.camera.y) / state.camera.zoom;
  const factor = event.deltaY < 0 ? 1.1 : 0.9;
  state.camera.zoom = Math.min(4, Math.max(.15, state.camera.zoom * factor));
  state.camera.x = mouseX - worldX * state.camera.zoom;
  state.camera.y = mouseY - worldY * state.camera.zoom;
  renderCamera();
}, { passive: false });

elements.boardViewport.addEventListener("dragover", (event) => {
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
});

elements.boardViewport.addEventListener("drop", async (event) => {
  event.preventDefault();
  const referenceId = event.dataTransfer.getData("application/x-reference-id");
  const reference = state.references.find((candidate) => candidate.id === referenceId);
  if (!reference) return;
  const point = viewportPointToBoard(event.clientX, event.clientY);
  await addReference(reference, point.x, point.y);
});

window.addEventListener("keydown", (event) => {
  const target = event.target;
  if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement) return;
  if ((event.key === "Delete" || event.key === "Backspace") && state.selectedId) {
    event.preventDefault();
    removeItem(state.selectedId);
  } else if (event.key === "Escape") {
    selectItem(null);
  }
});

window.addEventListener("pagehide", () => {
  for (const [boardId, timer] of state.saveTimers) {
    window.clearTimeout(timer);
    const board = state.boards.find((candidate) => candidate.id === boardId);
    if (!board) continue;
    fetch(`${API}/boards/${encodeURIComponent(board.id)}/items`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: boardItemsPayload(board) }),
      keepalive: true,
    });
  }
});

loadApplication().catch((error) => {
  console.error(error);
  setStatus("Failed to load", true);
  elements.referenceList.innerHTML = '<div class="library-message">The visualizer could not load its data.</div>';
});
