"""
Web-based viewer for photo organizer processing reports.

Uses Python stdlib http.server — no Flask or other dependencies required.
Proxies Immich thumbnails to avoid CORS issues and hide the API key.
"""

import json
import os
import sys
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# Will be set by start_viewer()
_report_path = None
_immich_client = None


def _load_report():
    """Load the processing report from disk."""
    try:
        with open(_report_path) as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e), "groups": [], "metadata": {}}


# ---------- Embedded HTML/JS frontend ----------

_FRONTEND_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Photo Organizer Viewer</title>
<style>
  :root { --accent: #4a90d9; --bg: #1a1a2e; --card: #16213e; --text: #e0e0e0; --best: #27ae60; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: var(--bg); color: var(--text); }
  header { background: var(--card); padding: 1rem 2rem; display: flex; align-items: center;
           justify-content: space-between; border-bottom: 2px solid var(--accent); }
  header h1 { font-size: 1.3rem; }
  .stats { font-size: 0.85rem; opacity: 0.7; }
  .controls { padding: 0.8rem 2rem; display: flex; gap: 1rem; align-items: center;
              background: var(--card); border-bottom: 1px solid #333; }
  .controls input[type=text] { padding: 0.4rem 0.8rem; border-radius: 4px; border: 1px solid #555;
                                background: #222; color: var(--text); width: 260px; }
  .controls label { font-size: 0.85rem; cursor: pointer; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          gap: 1rem; padding: 1.5rem 2rem; }
  .group-card { background: var(--card); border-radius: 8px; overflow: hidden;
                cursor: pointer; transition: transform 0.15s; border: 2px solid transparent; }
  .group-card:hover { transform: translateY(-2px); border-color: var(--accent); }
  .group-card.selected { border-color: #e67e22; }
  .group-header { padding: 0.6rem 0.8rem; font-size: 0.85rem; display: flex;
                  justify-content: space-between; align-items: center; }
  .group-header .label { font-weight: 600; }
  .group-header .person { color: var(--accent); }
  .thumbs { display: flex; overflow-x: auto; gap: 2px; padding: 2px; }
  .thumbs img { height: 100px; min-width: 70px; object-fit: cover; flex-shrink: 0; }
  .thumbs img.best { outline: 3px solid var(--best); outline-offset: -3px; }
  .group-footer { padding: 0.4rem 0.8rem; font-size: 0.75rem; opacity: 0.6;
                  display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .group-footer span { background: #333; padding: 2px 6px; border-radius: 3px; }

  /* Expanded detail view */
  .overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.85);
             z-index: 100; overflow-y: auto; }
  .overlay.show { display: block; }
  .detail { max-width: 1000px; margin: 2rem auto; background: var(--card);
            border-radius: 8px; padding: 1.5rem; }
  .detail h2 { margin-bottom: 1rem; }
  .detail-photos { display: flex; flex-wrap: wrap; gap: 0.8rem; margin-bottom: 1rem; }
  .detail-photo { text-align: center; cursor: pointer; position: relative; }
  .detail-photo img { height: 180px; border-radius: 4px; object-fit: cover; }
  .detail-photo.is-best img { outline: 4px solid var(--best); }
  .detail-photo .badge { position: absolute; top: 4px; right: 4px; background: var(--best);
                         color: #fff; font-size: 0.7rem; padding: 2px 6px; border-radius: 3px; }
  .detail-photo:hover .set-best-btn { display: block; }
  .set-best-btn { display: none; position: absolute; bottom: 4px; left: 50%; transform: translateX(-50%);
                  background: var(--accent); color: #fff; border: none; padding: 4px 10px;
                  border-radius: 3px; cursor: pointer; font-size: 0.75rem; white-space: nowrap; }
  .meta-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-top: 1rem; }
  .meta-table th, .meta-table td { padding: 4px 8px; text-align: left; border-bottom: 1px solid #333; }
  .meta-table th { color: var(--accent); }
  .actions-list { margin-top: 0.5rem; }
  .actions-list span { background: var(--best); color: #fff; padding: 2px 8px;
                       border-radius: 3px; font-size: 0.75rem; margin-right: 4px; }
  .close-btn { position: fixed; top: 1rem; right: 1.5rem; z-index: 110;
               background: #e74c3c; color: #fff; border: none; width: 36px; height: 36px;
               border-radius: 50%; cursor: pointer; font-size: 1.2rem; }

  /* Bulk bar */
  .bulk-bar { display: none; position: fixed; bottom: 0; left: 0; right: 0;
              background: var(--card); border-top: 2px solid var(--accent); padding: 0.8rem 2rem;
              z-index: 50; }
  .bulk-bar.show { display: flex; align-items: center; gap: 1rem; }
  .bulk-bar button { padding: 0.5rem 1rem; border: none; border-radius: 4px; cursor: pointer; }
  .btn-cleanup { background: #e74c3c; color: #fff; }
  .btn-cancel { background: #555; color: #fff; }
</style>
</head>
<body>

<header>
  <h1>Photo Organizer Viewer</h1>
  <div class="stats" id="stats"></div>
</header>

<div class="controls">
  <input type="text" id="search" placeholder="Filter by person, filename...">
  <label><input type="checkbox" id="bulkMode"> Bulk select</label>
</div>

<div class="grid" id="grid"></div>

<div class="overlay" id="overlay">
  <button class="close-btn" id="closeBtn">&times;</button>
  <div class="detail" id="detail"></div>
</div>

<div class="bulk-bar" id="bulkBar">
  <span id="bulkCount">0 selected</span>
  <button class="btn-cleanup" id="bulkCleanup">Cleanup Selected</button>
  <button class="btn-cancel" id="bulkCancel">Cancel</button>
</div>

<script>
let report = null;
let selectedGroups = new Set();

async function load() {
  const resp = await fetch('/api/report');
  report = await resp.json();
  render();
}

function render() {
  const meta = report.metadata || {};
  document.getElementById('stats').textContent =
    `${meta.total_groups || 0} groups | ${meta.total_photos || 0} photos | ` +
    `threshold: ${meta.similarity_threshold || '?'} | ${meta.generated_at || ''}`;

  const filter = document.getElementById('search').value.toLowerCase();
  const grid = document.getElementById('grid');
  grid.innerHTML = '';

  (report.groups || []).forEach(g => {
    const searchable = [
      g.person_name || '',
      ...g.photos.map(p => p.filename || '')
    ].join(' ').toLowerCase();
    if (filter && !searchable.includes(filter)) return;

    const card = document.createElement('div');
    card.className = 'group-card' + (selectedGroups.has(g.group_index) ? ' selected' : '');
    card.onclick = (e) => handleCardClick(e, g);

    const best = g.best_photo || {};
    card.innerHTML = `
      <div class="group-header">
        <span class="label">Group ${g.group_index} (${g.photo_count} photos)</span>
        ${g.person_name ? `<span class="person">${g.person_name}</span>` : ''}
      </div>
      <div class="thumbs">
        ${g.photos.map(p => `<img src="/api/thumbnail/${p.asset_id}"
          class="${p.is_best ? 'best' : ''}"
          alt="${p.filename || ''}"
          loading="lazy">`).join('')}
      </div>
      <div class="group-footer">
        ${g.actions_taken.map(a => `<span>${a}</span>`).join('')}
      </div>`;
    grid.appendChild(card);
  });
}

function handleCardClick(e, group) {
  if (document.getElementById('bulkMode').checked) {
    if (selectedGroups.has(group.group_index)) {
      selectedGroups.delete(group.group_index);
    } else {
      selectedGroups.add(group.group_index);
    }
    document.getElementById('bulkCount').textContent = selectedGroups.size + ' selected';
    document.getElementById('bulkBar').classList.toggle('show', selectedGroups.size > 0);
    render();
    return;
  }
  showDetail(group);
}

function showDetail(g) {
  const detail = document.getElementById('detail');
  const best = g.best_photo || {};
  const metaKeys = ['exif_Make','exif_Model','exif_DateTimeOriginal','exif_FNumber',
                     'exif_ExposureTime','exif_ISOSpeedRatings','dimensions','filesize'];

  let photosHtml = g.photos.map(p => `
    <div class="detail-photo ${p.is_best ? 'is-best' : ''}">
      <img src="/api/preview/${p.asset_id}" alt="${p.filename}">
      ${p.is_best ? '<span class="badge">BEST</span>' : ''}
      ${!p.is_best ? `<button class="set-best-btn" onclick="setBest(event, ${g.group_index}, '${p.asset_id}')">Set as Best</button>` : ''}
      <div style="font-size:0.75rem;margin-top:4px">${p.filename || p.id}</div>
    </div>`).join('');

  let metaRows = '';
  const headers = ['Photo', ...metaKeys];
  metaRows += '<tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr>';
  g.photos.forEach(p => {
    metaRows += '<tr><td>' + (p.filename || p.id) + (p.is_best ? ' *' : '') + '</td>';
    metaKeys.forEach(k => { metaRows += `<td>${p[k] || '-'}</td>`; });
    metaRows += '</tr>';
  });

  detail.innerHTML = `
    <h2>Group ${g.group_index}${g.person_name ? ' — ' + g.person_name : ''}</h2>
    <div class="detail-photos">${photosHtml}</div>
    <div class="actions-list">Actions: ${g.actions_taken.map(a => `<span>${a}</span>`).join('')}</div>
    <table class="meta-table">${metaRows}</table>`;

  document.getElementById('overlay').classList.add('show');
}

document.getElementById('closeBtn').onclick = () => {
  document.getElementById('overlay').classList.remove('show');
};
document.getElementById('overlay').onclick = (e) => {
  if (e.target === document.getElementById('overlay'))
    document.getElementById('overlay').classList.remove('show');
};
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') document.getElementById('overlay').classList.remove('show');
});

async function setBest(event, groupIndex, assetId) {
  event.stopPropagation();
  if (!confirm('Set this photo as the new best for the group? This will update tags and favorites in Immich.')) return;
  try {
    const resp = await fetch('/api/actions/set-best', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({group_index: groupIndex, asset_id: assetId})
    });
    const result = await resp.json();
    if (result.ok) {
      await load();
      alert('Best photo updated!');
    } else {
      alert('Error: ' + (result.error || 'Unknown error'));
    }
  } catch(e) { alert('Request failed: ' + e); }
}

document.getElementById('bulkCleanup').onclick = async () => {
  const indices = Array.from(selectedGroups);
  if (!confirm(`Run cleanup on ${indices.length} selected group(s)?`)) return;
  try {
    const resp = await fetch('/api/actions/bulk-cleanup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({group_indices: indices})
    });
    const result = await resp.json();
    alert(result.message || 'Cleanup complete');
    selectedGroups.clear();
    document.getElementById('bulkBar').classList.remove('show');
    await load();
  } catch(e) { alert('Request failed: ' + e); }
};

document.getElementById('bulkCancel').onclick = () => {
  selectedGroups.clear();
  document.getElementById('bulkBar').classList.remove('show');
  render();
};

document.getElementById('search').oninput = render;
document.getElementById('bulkMode').onchange = () => {
  if (!document.getElementById('bulkMode').checked) {
    selectedGroups.clear();
    document.getElementById('bulkBar').classList.remove('show');
    render();
  }
};

load();
</script>
</body>
</html>"""


class ViewerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the web viewer."""

    def log_message(self, format, *args):
        """Suppress default request logging."""
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_image(self, data, content_type="image/jpeg"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(data))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "":
            self._send_html(_FRONTEND_HTML)

        elif path == "/api/report":
            self._send_json(_load_report())

        elif path.startswith("/api/thumbnail/"):
            asset_id = path[len("/api/thumbnail/"):]
            self._proxy_image(asset_id, "thumbnail")

        elif path.startswith("/api/preview/"):
            asset_id = path[len("/api/preview/"):]
            self._proxy_image(asset_id, "preview")

        else:
            self.send_error(404)

    def _proxy_image(self, asset_id, size):
        """Proxy an Immich thumbnail/preview to avoid CORS."""
        if not _immich_client:
            self.send_error(503, "No Immich client configured")
            return
        data = _immich_client.get_asset_thumbnail(asset_id, size=size)
        if data:
            self._send_image(data)
        else:
            self.send_error(404, "Thumbnail not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        if path == "/api/actions/set-best":
            self._handle_set_best(body)
        elif path == "/api/actions/bulk-cleanup":
            self._handle_bulk_cleanup(body)
        else:
            self.send_error(404)

    def _handle_set_best(self, body):
        """Change the best photo for a group."""
        group_index = body.get("group_index")
        new_best_id = body.get("asset_id")

        if not _immich_client:
            self._send_json({"ok": False, "error": "No Immich client"}, 503)
            return

        report = _load_report()
        group = None
        for g in report.get("groups", []):
            if g["group_index"] == group_index:
                group = g
                break

        if not group:
            self._send_json({"ok": False, "error": "Group not found"}, 404)
            return

        old_best_id = group["best_photo"]["asset_id"]

        # Update tags: remove best from old, add to new; reverse for non-best
        best_tag_id = _immich_client.get_or_create_tag("photo-organizer/best")
        non_best_tag_id = _immich_client.get_or_create_tag("photo-organizer/non-best")

        if best_tag_id:
            _immich_client.tag_assets_by_tag_id(best_tag_id, [new_best_id])
        if non_best_tag_id:
            _immich_client.tag_assets_by_tag_id(non_best_tag_id, [old_best_id])

        # Update favorites
        _immich_client.update_asset(old_best_id, is_favorite=False)
        _immich_client.update_asset(new_best_id, is_favorite=True)

        # Update the report file
        group["best_photo"] = {
            "id": new_best_id, "asset_id": new_best_id,
            "filename": next((p["filename"] for p in group["photos"]
                              if p["asset_id"] == new_best_id), new_best_id),
        }
        for p in group["photos"]:
            p["is_best"] = (p["asset_id"] == new_best_id)

        try:
            with open(_report_path, "w") as f:
                json.dump(report, f, indent=2, default=str)
        except Exception as e:
            logging.warning(f"Failed to update report: {e}")

        self._send_json({"ok": True})

    def _handle_bulk_cleanup(self, body):
        """Cleanup selected groups: unfavorite, unarchive, remove tags."""
        indices = body.get("group_indices", [])
        if not _immich_client:
            self._send_json({"ok": False, "error": "No Immich client"}, 503)
            return

        report = _load_report()
        cleaned = 0
        for g in report.get("groups", []):
            if g["group_index"] not in indices:
                continue
            asset_ids = [p["asset_id"] for p in g["photos"]]
            # Unfavorite all, unarchive all
            _immich_client.bulk_update_assets(asset_ids, is_favorite=False, is_archived=False)
            cleaned += 1

        self._send_json({"ok": True, "message": f"Cleaned up {cleaned} group(s)"})


def start_viewer(report_path, port=8080, immich_client=None):
    """
    Start the web viewer server.

    Args:
        report_path: Path to processing_report.json
        port: HTTP port (default: 8080)
        immich_client: Optional ImmichClient for thumbnail proxying and actions
    """
    global _report_path, _immich_client
    _report_path = str(report_path)
    _immich_client = immich_client

    if not os.path.exists(_report_path):
        print(f"Error: Report file not found: {_report_path}")
        print("Run the organizer first to generate a processing report.")
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", port), ViewerHandler)
    print(f"\nPhoto Organizer Viewer running at http://localhost:{port}")
    print(f"Report: {_report_path}")
    if _immich_client:
        print(f"Immich: {_immich_client.url} (thumbnails enabled)")
    else:
        print("Note: No Immich client — thumbnails will not load")
    print("Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nViewer stopped.")
        server.server_close()
