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


def _save_report(report):
    """Save updated report back to disk."""
    try:
        with open(_report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
    except Exception as e:
        logging.warning(f"Failed to update report: {e}")


# ---------- Embedded HTML/JS frontend ----------

_FRONTEND_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Photo Organizer Viewer</title>
<style>
  :root { --accent: #4a90d9; --bg: #1a1a2e; --card: #16213e; --text: #e0e0e0; --best: #27ae60;
          --danger: #e74c3c; --warn: #e67e22; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: var(--bg); color: var(--text); }
  header { background: var(--card); padding: 1rem 2rem; display: flex; align-items: center;
           justify-content: space-between; border-bottom: 2px solid var(--accent); }
  header h1 { font-size: 1.3rem; }
  .stats { font-size: 0.85rem; opacity: 0.7; }
  .controls { padding: 0.8rem 2rem; display: flex; gap: 1rem; align-items: center;
              background: var(--card); border-bottom: 1px solid #333; flex-wrap: wrap; }
  .controls input[type=text] { padding: 0.4rem 0.8rem; border-radius: 4px; border: 1px solid #555;
                                background: #222; color: var(--text); width: 260px; }
  .controls label { font-size: 0.85rem; cursor: pointer; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
          gap: 1rem; padding: 1.5rem 2rem; }
  .group-card { background: var(--card); border-radius: 8px; overflow: hidden;
                cursor: pointer; transition: transform 0.15s; border: 2px solid transparent; }
  .group-card:hover { transform: translateY(-2px); border-color: var(--accent); }
  .group-card.selected { border-color: var(--warn); }
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
  .detail { max-width: 1100px; margin: 2rem auto; background: var(--card);
            border-radius: 8px; padding: 1.5rem; }
  .detail h2 { margin-bottom: 1rem; }
  .detail-photos { display: flex; flex-wrap: wrap; gap: 0.8rem; margin-bottom: 1rem; }
  .detail-photo { text-align: center; position: relative; }
  .detail-photo img { height: 180px; border-radius: 4px; object-fit: cover; cursor: pointer; }
  .detail-photo.is-best img { outline: 4px solid var(--best); }
  .detail-photo .badge { position: absolute; top: 4px; right: 4px; background: var(--best);
                         color: #fff; font-size: 0.7rem; padding: 2px 6px; border-radius: 3px; }
  .detail-photo .photo-actions { display: none; position: absolute; bottom: 24px; left: 50%;
                                 transform: translateX(-50%); display: flex; gap: 4px;
                                 opacity: 0; transition: opacity 0.15s; }
  .detail-photo:hover .photo-actions { opacity: 1; }
  .photo-actions button, .photo-actions a { background: var(--accent); color: #fff; border: none;
                padding: 4px 8px; border-radius: 3px; cursor: pointer; font-size: 0.7rem;
                text-decoration: none; white-space: nowrap; }
  .photo-actions a { background: #555; }
  .meta-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-top: 1rem;
                overflow-x: auto; display: block; }
  .meta-table th, .meta-table td { padding: 4px 8px; text-align: left; border-bottom: 1px solid #333;
                                    white-space: nowrap; }
  .meta-table th { color: var(--accent); position: sticky; top: 0; background: var(--card); }
  .actions-list { margin-top: 0.5rem; }
  .actions-list span { background: var(--best); color: #fff; padding: 2px 8px;
                       border-radius: 3px; font-size: 0.75rem; margin-right: 4px; }
  .close-btn { position: fixed; top: 1rem; right: 1.5rem; z-index: 110;
               background: var(--danger); color: #fff; border: none; width: 36px; height: 36px;
               border-radius: 50%; cursor: pointer; font-size: 1.2rem; }

  /* Full-size photo lightbox */
  .lightbox { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.95);
              z-index: 200; justify-content: center; align-items: center; cursor: zoom-out; }
  .lightbox.show { display: flex; }
  .lightbox img { max-width: 95vw; max-height: 95vh; object-fit: contain; }
  .lightbox .lb-close { position: fixed; top: 1rem; right: 1.5rem; background: var(--danger);
                        color: #fff; border: none; width: 36px; height: 36px; border-radius: 50%;
                        cursor: pointer; font-size: 1.2rem; z-index: 210; }
  .lightbox .lb-download { position: fixed; bottom: 1.5rem; right: 1.5rem; background: var(--accent);
                           color: #fff; border: none; padding: 8px 16px; border-radius: 4px;
                           cursor: pointer; font-size: 0.85rem; text-decoration: none; z-index: 210; }

  /* Bulk bar */
  .bulk-bar { display: none; position: fixed; bottom: 0; left: 0; right: 0;
              background: var(--card); border-top: 2px solid var(--accent); padding: 0.8rem 2rem;
              z-index: 50; }
  .bulk-bar.show { display: flex; align-items: center; gap: 0.8rem; flex-wrap: wrap; }
  .bulk-bar button { padding: 0.5rem 1rem; border: none; border-radius: 4px; cursor: pointer;
                     font-size: 0.85rem; }
  .btn-archive { background: var(--warn); color: #fff; }
  .btn-delete { background: var(--danger); color: #fff; }
  .btn-discard { background: #8e44ad; color: #fff; }
  .btn-cancel { background: #555; color: #fff; }
  .bulk-bar .sep { border-left: 1px solid #555; height: 24px; }

  /* Toast notification */
  .toast { position: fixed; bottom: 5rem; left: 50%; transform: translateX(-50%);
           background: var(--card); border: 1px solid var(--accent); padding: 0.6rem 1.2rem;
           border-radius: 6px; font-size: 0.85rem; z-index: 300; display: none; }
  .toast.show { display: block; }
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

<div class="lightbox" id="lightbox">
  <button class="lb-close" id="lbClose">&times;</button>
  <img id="lbImg" src="">
  <a class="lb-download" id="lbDownload" href="#" download>Download Full</a>
</div>

<div class="bulk-bar" id="bulkBar">
  <span id="bulkCount">0 selected</span>
  <div class="sep"></div>
  <button class="btn-archive" id="bulkArchive">Archive non-best</button>
  <button class="btn-delete" id="bulkDelete">Delete non-best</button>
  <button class="btn-discard" id="bulkDiscard">Discard changes</button>
  <div class="sep"></div>
  <button class="btn-cancel" id="bulkCancel">Cancel</button>
</div>

<div class="toast" id="toast"></div>

<script>
let report = null;
let selectedGroups = new Set();

function toast(msg, ms) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), ms || 3000);
}

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

  // Dynamically discover metadata columns from the photos
  const skipKeys = new Set(['id','asset_id','filename','is_best','hash']);
  const metaKeysSet = new Set();
  g.photos.forEach(p => {
    Object.keys(p).forEach(k => { if (!skipKeys.has(k)) metaKeysSet.add(k); });
  });
  // Sort: exif fields first (alphabetical), then others
  const metaKeys = Array.from(metaKeysSet).sort((a,b) => {
    const ae = a.startsWith('exif_'), be = b.startsWith('exif_');
    if (ae && !be) return -1;
    if (!ae && be) return 1;
    return a.localeCompare(b);
  });

  // Nice display names for common keys
  const labels = {
    'exif_make': 'Make', 'exif_model': 'Model', 'exif_dateTimeOriginal': 'Date/Time',
    'exif_fNumber': 'f/', 'exif_exposureTime': 'Shutter', 'exif_iso': 'ISO',
    'exif_focalLength': 'Focal', 'exif_lensModel': 'Lens',
    'exif_exifImageWidth': 'Width', 'exif_exifImageHeight': 'Height',
    'exif_fileSizeInByte': 'Size (bytes)', 'filesize': 'File Size',
    'dimensions': 'Dimensions',
  };

  let photosHtml = g.photos.map(p => `
    <div class="detail-photo ${p.is_best ? 'is-best' : ''}">
      <img src="/api/preview/${p.asset_id}" alt="${p.filename}"
           onclick="openLightbox('${p.asset_id}', '${p.filename || p.id}')">
      ${p.is_best ? '<span class="badge">BEST</span>' : ''}
      <div class="photo-actions">
        ${!p.is_best ? `<button onclick="setBest(event, ${g.group_index}, '${p.asset_id}')">Set Best</button>` : ''}
        <a href="/api/full/${p.asset_id}" target="_blank" onclick="event.stopPropagation()">Full</a>
      </div>
      <div style="font-size:0.75rem;margin-top:4px">${p.filename || p.id}</div>
    </div>`).join('');

  let metaRows = '<tr><th>Photo</th>' + metaKeys.map(h =>
    `<th>${labels[h] || h.replace('exif_','')}</th>`).join('') + '</tr>';
  g.photos.forEach(p => {
    metaRows += '<tr><td>' + (p.filename || p.id) + (p.is_best ? ' *' : '') + '</td>';
    metaKeys.forEach(k => {
      let v = p[k];
      if (v !== undefined && v !== null && v !== '') {
        // Format file sizes
        if ((k === 'filesize' || k === 'exif_fileSizeInByte') && !isNaN(v)) {
          v = (Number(v) / 1024 / 1024).toFixed(1) + ' MB';
        }
        metaRows += `<td>${v}</td>`;
      } else {
        metaRows += '<td>-</td>';
      }
    });
    metaRows += '</tr>';
  });

  detail.innerHTML = `
    <h2>Group ${g.group_index}${g.person_name ? ' &mdash; ' + g.person_name : ''}</h2>
    <div class="detail-photos">${photosHtml}</div>
    <div class="actions-list">Actions: ${g.actions_taken.map(a => `<span>${a}</span>`).join('')}</div>
    <table class="meta-table">${metaRows}</table>`;

  document.getElementById('overlay').classList.add('show');
}

/* Lightbox for full-resolution photo viewing */
function openLightbox(assetId, filename) {
  const lb = document.getElementById('lightbox');
  const img = document.getElementById('lbImg');
  const dl = document.getElementById('lbDownload');
  img.src = '/api/preview/' + assetId;
  dl.href = '/api/full/' + assetId;
  dl.download = filename || 'photo.jpg';
  lb.classList.add('show');
}

document.getElementById('lbClose').onclick = (e) => {
  e.stopPropagation();
  document.getElementById('lightbox').classList.remove('show');
};
document.getElementById('lightbox').onclick = (e) => {
  if (e.target === document.getElementById('lightbox'))
    document.getElementById('lightbox').classList.remove('show');
};

document.getElementById('closeBtn').onclick = () => {
  document.getElementById('overlay').classList.remove('show');
};
document.getElementById('overlay').onclick = (e) => {
  if (e.target === document.getElementById('overlay'))
    document.getElementById('overlay').classList.remove('show');
};
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.getElementById('lightbox').classList.remove('show');
    document.getElementById('overlay').classList.remove('show');
  }
});

async function setBest(event, groupIndex, assetId) {
  event.stopPropagation();
  if (!confirm('Set this photo as the new best? This updates tags and favorites in Immich.')) return;
  try {
    const resp = await fetch('/api/actions/set-best', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({group_index: groupIndex, asset_id: assetId})
    });
    const result = await resp.json();
    if (result.ok) {
      await load();
      toast('Best photo updated');
    } else {
      alert('Error: ' + (result.error || 'Unknown error'));
    }
  } catch(e) { alert('Request failed: ' + e); }
}

/* Bulk actions */
async function bulkAction(action) {
  const indices = Array.from(selectedGroups);
  const labels = {
    'archive-non-best': `Archive non-best photos in ${indices.length} group(s)?`,
    'delete-non-best': `PERMANENTLY DELETE non-best photos in ${indices.length} group(s)? This cannot be undone!`,
    'discard': `Discard organizer changes for ${indices.length} group(s)? This will unfavorite, unarchive, and remove tags.`,
  };
  if (!confirm(labels[action] || `Run ${action} on ${indices.length} group(s)?`)) return;
  try {
    const resp = await fetch('/api/actions/bulk', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: action, group_indices: indices})
    });
    const result = await resp.json();
    toast(result.message || 'Done');
    selectedGroups.clear();
    document.getElementById('bulkBar').classList.remove('show');
    await load();
  } catch(e) { alert('Request failed: ' + e); }
}

document.getElementById('bulkArchive').onclick = () => bulkAction('archive-non-best');
document.getElementById('bulkDelete').onclick = () => bulkAction('delete-non-best');
document.getElementById('bulkDiscard').onclick = () => bulkAction('discard');

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

        elif path.startswith("/api/full/"):
            asset_id = path[len("/api/full/"):]
            self._proxy_full(asset_id)

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

    def _proxy_full(self, asset_id):
        """Proxy full-resolution download from Immich."""
        if not _immich_client:
            self.send_error(503, "No Immich client configured")
            return
        data = _immich_client.download_asset(asset_id)
        if data:
            self._send_image(data, content_type="image/jpeg")
        else:
            self.send_error(404, "Asset not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        if path == "/api/actions/set-best":
            self._handle_set_best(body)
        elif path == "/api/actions/bulk":
            self._handle_bulk(body)
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

        # Update tags: add best to new, add non-best to old
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

        _save_report(report)
        self._send_json({"ok": True})

    def _handle_bulk(self, body):
        """Handle bulk actions: archive-non-best, delete-non-best, discard."""
        action = body.get("action")
        indices = body.get("group_indices", [])

        if not _immich_client:
            self._send_json({"ok": False, "error": "No Immich client"}, 503)
            return

        report = _load_report()
        affected = 0
        asset_count = 0

        for g in report.get("groups", []):
            if g["group_index"] not in indices:
                continue
            affected += 1

            best_id = g["best_photo"]["asset_id"]
            all_ids = [p["asset_id"] for p in g["photos"]]
            non_best_ids = [aid for aid in all_ids if aid != best_id]

            if action == "archive-non-best":
                if non_best_ids:
                    _immich_client.bulk_update_assets(non_best_ids, is_archived=True)
                    asset_count += len(non_best_ids)

            elif action == "delete-non-best":
                if non_best_ids:
                    _immich_client.bulk_delete_assets(non_best_ids, force=False)
                    asset_count += len(non_best_ids)

            elif action == "discard":
                # Unfavorite all, unarchive all
                _immich_client.bulk_update_assets(all_ids, is_favorite=False, is_archived=False)
                asset_count += len(all_ids)
                # Remove tags for this group
                group_tag_name = f"photo-organizer/group-{g['group_index']:04d}"
                for tag_name in [group_tag_name]:
                    tags = _immich_client.get_tags()
                    for t in tags:
                        if (t.get('name') or t.get('value', '')) == tag_name:
                            _immich_client.delete_tag(t['id'])
                            break

        messages = {
            "archive-non-best": f"Archived {asset_count} non-best photo(s) in {affected} group(s)",
            "delete-non-best": f"Trashed {asset_count} non-best photo(s) in {affected} group(s)",
            "discard": f"Discarded changes for {affected} group(s) ({asset_count} assets unfavorited/unarchived)",
        }
        self._send_json({"ok": True, "message": messages.get(action, "Done")})


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
        print(f"Immich: {_immich_client.url} (thumbnails + full photos enabled)")
    else:
        print("Note: No Immich client — thumbnails will not load")
    print("Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nViewer stopped.")
        server.server_close()
