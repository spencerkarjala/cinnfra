INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Reference Compiler</title>
    <style>
        body {{
            font-family: system-ui, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #1a1a1a;
            color: #e0e0e0;
        }}
        h1, h2 {{ color: #fff; }}
        form {{ margin: 20px 0; }}
        input[type="url"] {{
            width: 100%;
            padding: 12px;
            font-size: 16px;
            border: 1px solid #444;
            border-radius: 4px;
            background: #2a2a2a;
            color: #e0e0e0;
            box-sizing: border-box;
        }}
        button {{
            margin-top: 10px;
            padding: 12px 24px;
            font-size: 16px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }}
        button:hover {{ background: #0055aa; }}
        .delete-btn {{
            background: #cc3333;
            padding: 6px 12px;
            font-size: 14px;
            margin: 0;
        }}
        .delete-btn:hover {{ background: #aa2222; }}
        .result, .reference {{
            margin-top: 20px;
            padding: 15px;
            background: #2a2a2a;
            border-radius: 4px;
        }}
        .result img, .reference img {{
            max-width: 200px;
            margin-top: 10px;
            border-radius: 4px;
        }}
        .reference {{
            display: flex;
            gap: 15px;
            align-items: flex-start;
        }}
        .reference-info {{
            flex: 1;
        }}
        .reference-info p {{
            margin: 5px 0;
        }}
        .error {{ color: #ff6b6b; }}
        a {{ color: #66b3ff; }}
        hr {{ border-color: #444; margin: 30px 0; }}
        .media-type {{ color: #888; font-size: 12px; }}
    </style>
</head>
<body>
    <h1>Reference Compiler</h1>
    <form method="post" action="/">
        <input type="url" name="url" placeholder="https://..." required>
        <button type="submit">Fetch</button>
    </form>
    {result}
    <hr>
    <h2>Saved References</h2>
    {references}
</body>
</html>
"""


def render_references_html(references: list[dict]) -> str:
    if not references:
        return "<p>No references saved yet.</p>"

    html_parts = []
    for ref in references:
        html_parts.append(f'''
        <div class="reference">
            <img src="/artwork/{ref["filename"]}" alt="Artwork">
            <div class="reference-info">
                <p><strong>{ref["artist"]}</strong> - {ref["track_name"]}</p>
                <p class="media-type">{ref["media_type"]}</p>
                <p><a href="{ref["url"]}" target="_blank">Source</a></p>
                <form method="post" action="/delete/{ref["id"]}" style="margin:0">
                    <button type="submit" class="delete-btn">Delete</button>
                </form>
            </div>
        </div>
        ''')
    return "".join(html_parts)


def render_index(result: str, references: list[dict]) -> str:
    return INDEX_HTML.format(result=result, references=render_references_html(references))


def render_result_html(saved_items: list[tuple[str, any, str]]) -> str:
    result_parts = []
    for action, result, filename in saved_items:
        result_parts.append(f'''
        <div class="result">
            <p>{action}: <strong>{result.artist}</strong> - {result.track_name}</p>
            <p class="media-type">{result.media_type}</p>
            <img src="/artwork/{filename}" alt="Artwork">
        </div>
        ''')
    return "".join(result_parts)


def render_error_html(message: str) -> str:
    return f'<div class="result error">{message}</div>'
