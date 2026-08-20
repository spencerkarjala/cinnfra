import html
import json
from typing import Any


INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Reference Compiler</title>
    <style>
        body {
            font-family: system-ui, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #1a1a1a;
            color: #e0e0e0;
        }
        h1, h2 { color: #fff; }
        form { margin: 20px 0; }
        input[type="url"], input[type="text"] {
            width: 100%;
            padding: 12px;
            font-size: 16px;
            border: 1px solid #444;
            border-radius: 4px;
            background: #2a2a2a;
            color: #e0e0e0;
            box-sizing: border-box;
        }
        button {
            margin-top: 10px;
            padding: 12px 24px;
            font-size: 16px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        button:hover { background: #0055aa; }
        button:disabled { cursor: wait; opacity: .65; }
        .secondary-btn { background: #444; }
        .secondary-btn:hover { background: #555; }
        .delete-btn {
            background: #cc3333;
            padding: 6px 12px;
            font-size: 14px;
            margin: 0;
        }
        .delete-btn:hover { background: #aa2222; }
        .result, .reference {
            margin-top: 20px;
            padding: 15px;
            background: #2a2a2a;
            border-radius: 4px;
        }
        .result img, .reference img,
        .result video, .reference video {
            max-width: 200px;
            max-height: 240px;
            object-fit: contain;
            margin-top: 10px;
            border-radius: 4px;
        }
        .reference {
            display: flex;
            gap: 15px;
            align-items: flex-start;
        }
        .reference-info { flex: 1; min-width: 0; }
        .reference-info p { margin: 5px 0; }
        .error { color: #ff6b6b; }
        a { color: #66b3ff; }
        hr { border-color: #444; margin: 30px 0; }
        .media-type { color: #888; font-size: 12px; }
        .section-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }
        .section-heading h2 { margin: 0; }
        .section-heading button { margin: 0; padding: 8px 12px; font-size: 14px; }
        .tag-list {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 8px;
            margin: 12px 0;
        }
        .tag-chip, .tag-option {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            width: auto;
            margin: 0;
            padding: 5px 10px;
            border: 1px solid #555;
            border-radius: 999px;
            background: #363636;
            color: #ddd;
            font-size: 13px;
            line-height: 1.2;
        }
        .tag-option:hover { background: #464646; }
        .tag-option[aria-pressed="true"] {
            border-color: #3391ff;
            background: #0d579f;
            color: #fff;
        }
        .add-tag-btn {
            width: auto;
            margin: 0;
            padding: 5px 10px;
            border: 1px dashed #777;
            border-radius: 999px;
            background: transparent;
            color: #9dccff;
            font-size: 13px;
        }
        .add-tag-btn:hover { background: #363636; }
        dialog {
            width: min(520px, calc(100vw - 40px));
            padding: 0;
            border: 1px solid #555;
            border-radius: 8px;
            background: #252525;
            color: #e0e0e0;
            box-shadow: 0 18px 60px #000a;
        }
        dialog::backdrop { background: #000a; }
        .modal-content { padding: 20px; }
        .modal-heading {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }
        .modal-heading h2 { margin: 0; }
        .close-btn, .chip-action {
            width: auto;
            margin: 0;
            padding: 4px 8px;
            background: transparent;
            color: #bbb;
            font-size: 18px;
        }
        .close-btn:hover, .chip-action:hover { background: #444; }
        .modal-actions {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            margin-top: 20px;
        }
        .modal-actions button { margin: 0; }
        .manage-tag { padding-right: 3px; }
        .manage-tag .chip-action { padding: 1px 5px; font-size: 14px; }
        .manage-tag .remove-tag { color: #ff8c8c; }
        .create-tag-form {
            display: flex;
            gap: 8px;
            margin: 16px 0 0;
        }
        .create-tag-form input { flex: 1; }
        .create-tag-form button { margin: 0; padding: 8px 14px; }
        .muted { color: #999; font-size: 14px; }
        @media (max-width: 600px) {
            body { margin: 20px auto; }
            .reference { flex-direction: column; }
            .reference img, .reference video { max-width: 100%; }
        }
    </style>
</head>
<body>
    <h1>Reference Compiler</h1>
    <form method="post" action="/">
        <input type="url" name="url" placeholder="https://..." required>
        <button type="submit">Fetch</button>
    </form>
    __RESULT__
    <hr>
    <div class="section-heading">
        <h2>Saved References</h2>
        <button type="button" class="secondary-btn" id="manage-tags-btn">Manage tags</button>
    </div>
    __REFERENCES__

    <dialog id="tag-dialog">
        <div class="modal-content">
            <div class="modal-heading">
                <h2>Add tags</h2>
                <button type="button" class="close-btn" data-close-dialog aria-label="Close">×</button>
            </div>
            <p class="muted">Select every tag that should be applied to this reference.</p>
            <div class="tag-list" id="tag-options">__TAG_OPTIONS__</div>
            <div class="modal-actions">
                <button type="button" class="secondary-btn" data-close-dialog>Cancel</button>
                <button type="button" id="apply-tags-btn">Apply</button>
            </div>
        </div>
    </dialog>

    <dialog id="tag-manager-dialog">
        <div class="modal-content">
            <div class="modal-heading">
                <h2>Manage tags</h2>
                <button type="button" class="close-btn" data-close-dialog aria-label="Close">×</button>
            </div>
            <div class="tag-list">__MANAGED_TAGS__</div>
            <form class="create-tag-form" id="create-tag-form">
                <input type="text" id="new-tag-name" maxlength="50" placeholder="New tag name" required>
                <button type="submit">Create</button>
            </form>
        </div>
    </dialog>

    <script>
        const tagDialog = document.getElementById("tag-dialog");
        const tagManagerDialog = document.getElementById("tag-manager-dialog");
        let activeReferenceId = null;

        async function apiRequest(url, options) {
            const response = await fetch(url, options);
            let payload = null;
            try { payload = await response.json(); } catch (_) { /* no response body */ }
            if (!response.ok) {
                throw new Error(payload?.detail || "The request failed");
            }
            return payload;
        }

        document.querySelectorAll(".open-tag-dialog").forEach((button) => {
            button.addEventListener("click", () => {
                activeReferenceId = button.dataset.referenceId;
                const selectedIds = new Set(JSON.parse(button.dataset.tagIds));
                document.querySelectorAll(".tag-option").forEach((option) => {
                    option.setAttribute("aria-pressed", selectedIds.has(option.dataset.tagId));
                });
                tagDialog.showModal();
            });
        });

        document.querySelectorAll(".tag-option").forEach((option) => {
            option.addEventListener("click", () => {
                option.setAttribute("aria-pressed", option.getAttribute("aria-pressed") !== "true");
            });
        });

        document.getElementById("apply-tags-btn").addEventListener("click", async (event) => {
            if (!activeReferenceId) return;
            const button = event.currentTarget;
            const tagIds = [...document.querySelectorAll('.tag-option[aria-pressed="true"]')]
                .map((option) => option.dataset.tagId);
            button.disabled = true;
            try {
                await apiRequest(`/reference/${encodeURIComponent(activeReferenceId)}/tags`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ tag_ids: tagIds }),
                });
                window.location.reload();
            } catch (error) {
                alert(error.message);
                button.disabled = false;
            }
        });

        document.getElementById("manage-tags-btn").addEventListener("click", () => {
            tagManagerDialog.showModal();
        });

        document.querySelectorAll("[data-close-dialog]").forEach((button) => {
            button.addEventListener("click", () => button.closest("dialog").close());
        });

        document.getElementById("create-tag-form").addEventListener("submit", async (event) => {
            event.preventDefault();
            const input = document.getElementById("new-tag-name");
            try {
                await apiRequest("/tags", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ display_name: input.value }),
                });
                window.location.reload();
            } catch (error) {
                alert(error.message);
            }
        });

        document.querySelectorAll(".rename-tag").forEach((button) => {
            button.addEventListener("click", async () => {
                const displayName = prompt("Tag display name", button.dataset.tagName);
                if (displayName === null || !displayName.trim()) return;
                try {
                    await apiRequest(`/tags/${encodeURIComponent(button.dataset.tagId)}`, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ display_name: displayName }),
                    });
                    window.location.reload();
                } catch (error) {
                    alert(error.message);
                }
            });
        });

        document.querySelectorAll(".remove-tag").forEach((button) => {
            button.addEventListener("click", async () => {
                if (!confirm(`Delete the tag “${button.dataset.tagName}”?`)) return;
                try {
                    await apiRequest(`/tags/${encodeURIComponent(button.dataset.tagId)}`, {
                        method: "DELETE",
                    });
                    window.location.reload();
                } catch (error) {
                    alert(error.message);
                }
            });
        });
    </script>
</body>
</html>
"""


VIDEO_EXTENSIONS = {"m4v", "mov", "mp4", "webm"}


def render_media_html(filename: str) -> str:
    escaped_filename = html.escape(filename, quote=True)
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension in VIDEO_EXTENSIONS:
        return f'<video src="/artwork/{escaped_filename}" controls muted loop></video>'
    return f'<img src="/artwork/{escaped_filename}" alt="Artwork">'


def render_references_html(references: list[dict]) -> str:
    if not references:
        return "<p>No references saved yet.</p>"

    html_parts = []
    for ref in references:
        tags = ref.get("tags", [])
        selected_ids = html.escape(
            json.dumps([tag["id"] for tag in tags]), quote=True
        )
        tag_chips = "".join(
            f'<span class="tag-chip">{html.escape(tag["display_name"])}</span>'
            for tag in tags
        )
        reference_id = html.escape(ref["id"], quote=True)
        tag_controls = f'''
            <div class="tag-list">
                {tag_chips}
                <button type="button" class="add-tag-btn open-tag-dialog"
                        data-reference-id="{reference_id}" data-tag-ids="{selected_ids}">+ Add tag</button>
            </div>
        '''
        html_parts.append(f'''
        <div class="reference">
            {render_media_html(ref["filename"])}
            <div class="reference-info">
                <p><strong>{html.escape(ref["artist"])}</strong> - {html.escape(ref["track_name"])}</p>
                <p class="media-type">{html.escape(ref["media_type"])}</p>
                <p><a href="{html.escape(ref["url"], quote=True)}" target="_blank" rel="noopener">Source</a></p>
                {tag_controls}
                <form method="post" action="/delete/{reference_id}" style="margin:0">
                    <button type="submit" class="delete-btn">Delete</button>
                </form>
            </div>
        </div>
        ''')
    return "".join(html_parts)


def render_tag_options(tags: list[dict]) -> str:
    if not tags:
        return '<p class="muted">No tags yet. Create one in Manage tags.</p>'
    return "".join(
        f'<button type="button" class="tag-option" aria-pressed="false" '
        f'data-tag-id="{html.escape(tag["id"], quote=True)}">'
        f'{html.escape(tag["display_name"])}</button>'
        for tag in tags
    )


def render_managed_tags(tags: list[dict]) -> str:
    if not tags:
        return '<p class="muted">No tags created yet.</p>'

    parts = []
    for tag in tags:
        tag_id = html.escape(tag["id"], quote=True)
        display_name = html.escape(tag["display_name"])
        data_name = html.escape(tag["display_name"], quote=True)
        parts.append(f'''
            <span class="tag-chip manage-tag">
                <span>{display_name}</span>
                <button type="button" class="chip-action rename-tag" data-tag-id="{tag_id}"
                        data-tag-name="{data_name}" aria-label="Rename {data_name}" title="Rename">✎</button>
                <button type="button" class="chip-action remove-tag" data-tag-id="{tag_id}"
                        data-tag-name="{data_name}" aria-label="Delete {data_name}" title="Delete">×</button>
            </span>
        ''')
    return "".join(parts)


def render_index(result: str, references: list[dict], tags: list[dict]) -> str:
    return (
        INDEX_HTML.replace("__RESULT__", result)
        .replace("__REFERENCES__", render_references_html(references))
        .replace("__TAG_OPTIONS__", render_tag_options(tags))
        .replace("__MANAGED_TAGS__", render_managed_tags(tags))
    )


def render_result_html(saved_items: list[tuple[str, Any, str]]) -> str:
    result_parts = []
    for action, result, filename in saved_items:
        result_parts.append(f'''
        <div class="result">
            <p>{html.escape(action)}: <strong>{html.escape(result.artist)}</strong> - {html.escape(result.track_name)}</p>
            <p class="media-type">{html.escape(result.media_type)}</p>
            {render_media_html(filename)}
        </div>
        ''')
    return "".join(result_parts)


def render_error_html(message: str) -> str:
    return f'<div class="result error">{html.escape(message)}</div>'
