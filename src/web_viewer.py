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
_report_dir = None
_immich_client = None
_local_file_cache = {}  # {asset_id: filepath}


def _build_local_file_cache():
    """Build a mapping of asset_id -> local filepath from the report."""
    global _local_file_cache
    _local_file_cache = {}
    try:
        with open(_report_path) as f:
            report = json.load(f)
        for group in report.get('groups', []):
            for photo in group.get('photos', []):
                asset_id = photo.get('asset_id')
                filepath = photo.get('filepath') or photo.get('local_path')
                if asset_id and filepath:
                    _local_file_cache[asset_id] = filepath
    except Exception:
        pass


def _get_local_filepath(asset_id: str):
    """Get local filepath for an asset_id if available."""
    if not _local_file_cache:
        _build_local_file_cache()
    return _local_file_cache.get(asset_id)


def _generate_thumbnail(filepath: str, max_size: int = 250):
    """Generate a thumbnail from a local image file."""
    try:
        from PIL import Image
        import io

        img = Image.open(filepath)
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        # Handle RGBA images (convert to RGB for JPEG)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        return buffer.getvalue()
    except ImportError:
        # PIL not available - return full file
        return Path(filepath).read_bytes() if Path(filepath).exists() else None
    except Exception:
        return None


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

  /* Tab bar */
  .tab-bar { display: flex; gap: 0; background: var(--card); border-bottom: 1px solid #333; }
  .tab-bar button { padding: 0.6rem 1.5rem; border: none; background: transparent; color: var(--text);
                    cursor: pointer; font-size: 0.9rem; border-bottom: 2px solid transparent;
                    opacity: 0.6; transition: all 0.15s; }
  .tab-bar button.active { border-bottom-color: var(--accent); opacity: 1; font-weight: 600; }
  .tab-bar button:hover { opacity: 0.9; }

  /* People view */
  .people-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
                 gap: 1rem; padding: 1.5rem 2rem; }
  .person-card { background: var(--card); border-radius: 8px; overflow: hidden; cursor: pointer;
                 transition: transform 0.15s; border: 2px solid transparent; text-align: center; }
  .person-card:hover { transform: translateY(-2px); border-color: var(--accent); }
  .person-card img { width: 100%; height: 160px; object-fit: cover; }
  .person-card .person-info { padding: 0.5rem; }
  .person-card .person-name { font-weight: 600; font-size: 0.9rem; }
  .person-card .person-count { font-size: 0.75rem; opacity: 0.6; }
  .person-photos { padding: 1.5rem 2rem; }
  .person-photos h3 { margin-bottom: 1rem; }
  .person-photos .back-btn { background: var(--accent); color: #fff; border: none; padding: 0.4rem 1rem;
                              border-radius: 4px; cursor: pointer; margin-bottom: 1rem; font-size: 0.85rem; }
  .person-photo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                       gap: 0.5rem; }
  .person-photo-grid img { width: 100%; height: 140px; object-fit: cover; border-radius: 4px;
                           cursor: pointer; }

  /* Toast notification */
  .toast { position: fixed; bottom: 5rem; left: 50%; transform: translateX(-50%);
           background: var(--card); border: 1px solid var(--accent); padding: 0.6rem 1.2rem;
           border-radius: 6px; font-size: 0.85rem; z-index: 300; display: none; }
  .toast.show { display: block; }

  /* Merge / reprocess bulk bar buttons */
  .btn-merge { background: #2980b9; color: #fff; }
  .btn-reprocess { background: #16a085; color: #fff; }

  /* Reprocess modal */
  .modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.85);
           z-index: 150; justify-content: center; align-items: center; }
  .modal.show { display: flex; }
  .modal-box { background: var(--card); border-radius: 8px; padding: 1.5rem;
               max-width: 420px; width: 90%; }
  .modal-box h3 { margin-bottom: 1rem; font-size: 1.1rem; }
  .radio-group { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.2rem; }
  .radio-group label { cursor: pointer; display: flex; align-items: center; gap: 0.5rem;
                       padding: 0.4rem 0.6rem; border-radius: 4px; }
  .radio-group label:hover { background: #333; }
  .modal-actions { display: flex; gap: 0.5rem; justify-content: flex-end; }

  /* Photo selection checkboxes in detail view (for split) */
  .photo-checkbox { position: absolute; top: 4px; left: 4px; width: 18px; height: 18px;
                    cursor: pointer; z-index: 5; accent-color: var(--accent); }
  .split-bar { margin-top: 0.8rem; display: none; align-items: center; gap: 0.8rem; }
  .split-bar.show { display: flex; }
  .btn-split { background: #8e44ad; color: #fff; border: none; padding: 0.5rem 1rem;
               border-radius: 4px; cursor: pointer; font-size: 0.85rem; }
</style>
</head>
<body>

<header>
  <h1>Photo Organizer Viewer</h1>
  <div class="stats" id="stats"></div>
</header>

<div class="tab-bar">
  <button class="active" id="tabGroups" onclick="switchTab('groups')">Groups</button>
  <button id="tabPeople" onclick="switchTab('people')">People</button>
</div>

<div id="groupsView">
  <div class="controls">
    <select id="reportSelect" style="padding:0.4rem;border-radius:4px;border:1px solid #555;background:#222;color:var(--text);"></select>
    <input type="text" id="search" placeholder="Filter by person, filename...">
    <label><input type="checkbox" id="bulkMode"> Bulk select</label>
  </div>
  <div class="grid" id="grid"></div>
</div>

<div id="peopleView" style="display:none;">
  <div class="people-grid" id="peopleGrid"></div>
  <div class="person-photos" id="personPhotos" style="display:none;"></div>
</div>

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
  <button class="btn-merge" id="bulkMerge" style="display:none" onclick="mergeGroups()">Merge groups</button>
  <button class="btn-reprocess" id="bulkReprocess" onclick="showReprocessModal()">Reprocess...</button>
  <div class="sep"></div>
  <button class="btn-cancel" id="bulkCancel">Cancel</button>
</div>

<!-- Reprocess modal -->
<div class="modal" id="reprocessModal">
  <div class="modal-box">
    <h3>Reprocess: Pick Best Photo By</h3>
    <div class="radio-group">
      <label><input type="radio" name="criteria" value="filesize" checked> Largest file size</label>
      <label><input type="radio" name="criteria" value="dimensions"> Largest dimensions (resolution)</label>
      <label><input type="radio" name="criteria" value="date_oldest"> Oldest date (first in burst)</label>
      <label><input type="radio" name="criteria" value="date_newest"> Newest date (last in burst)</label>
    </div>
    <div class="modal-actions">
      <button class="btn-cancel" style="padding:0.5rem 1rem;border:none;border-radius:4px;cursor:pointer"
              onclick="document.getElementById('reprocessModal').classList.remove('show')">Cancel</button>
      <button style="background:var(--accent);color:#fff;border:none;padding:0.5rem 1rem;border-radius:4px;cursor:pointer"
              onclick="reprocessGroups()">Apply to Selected</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let report = null;
let selectedGroups = new Set();
let currentReportFile = null;

function toast(msg, ms) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), ms || 3000);
}

async function loadReportList() {
  try {
    const resp = await fetch('/api/reports');
    const reports = await resp.json();
    const sel = document.getElementById('reportSelect');
    sel.innerHTML = '<option value="">Current report</option>';
    reports.forEach(r => {
      const opt = document.createElement('option');
      opt.value = r.filename;
      const date = r.generated_at ? r.generated_at.replace('T', ' ').substring(0, 19) : r.filename;
      const summary = r.settings_summary
        ? ` (t=${r.settings_summary.threshold || '?'}, ${r.total_groups || 0} groups)`
        : '';
      opt.textContent = date + summary;
      sel.appendChild(opt);
    });
    sel.onchange = async () => {
      currentReportFile = sel.value;
      await load();
    };
  } catch(e) { /* reports dir may not exist */ }
}

async function load() {
  let url = '/api/report';
  if (currentReportFile) {
    url = '/api/report/' + currentReportFile;
  }
  const resp = await fetch(url);
  report = await resp.json();
  render();
}

function render() {
  const meta = report.metadata || {};
  const settings = report.settings || {};
  let statsText = `${meta.total_groups || 0} groups | ${meta.total_photos || 0} photos | ` +
    `threshold: ${settings.similarity_threshold || meta.similarity_threshold || '?'}`;
  if (settings.limit) statsText += ` | limit: ${settings.limit}`;
  if (settings.source_type) statsText += ` | ${settings.source_type}`;
  statsText += ` | ${meta.generated_at || ''}`;
  document.getElementById('stats').textContent = statsText;

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
    // Show merge button only when 2+ groups selected
    document.getElementById('bulkMerge').style.display = selectedGroups.size >= 2 ? '' : 'none';
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
      <input type="checkbox" class="photo-checkbox" value="${p.asset_id}"
             onchange="updateSplitBtn(${g.group_index})">
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
    <div class="split-bar" id="splitBar">
      <button class="btn-split" onclick="splitSelectedPhotos(${g.group_index})">Split selected to new group</button>
      <span id="splitCount" style="font-size:0.8rem;opacity:0.7"></span>
    </div>
    <div class="actions-list" style="margin-top:0.5rem">Actions: ${g.actions_taken.map(a => `<span>${a}</span>`).join('')}</div>
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
  document.getElementById('bulkMerge').style.display = 'none';
  render();
};

/* Merge selected groups into one */
async function mergeGroups() {
  const indices = Array.from(selectedGroups);
  if (indices.length < 2) return;
  if (!confirm(`Merge ${indices.length} groups into one? The lowest-numbered group will absorb the others.`)) return;
  try {
    const resp = await fetch('/api/actions/merge-groups', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({group_indices: indices})
    });
    const result = await resp.json();
    if (result.ok) {
      toast('Groups merged into group ' + result.merged_index);
      selectedGroups.clear();
      document.getElementById('bulkBar').classList.remove('show');
      document.getElementById('bulkMerge').style.display = 'none';
      await load();
    } else {
      alert('Error: ' + (result.error || 'Unknown error'));
    }
  } catch(e) { alert('Request failed: ' + e); }
}

/* Reprocess modal */
function showReprocessModal() {
  if (!selectedGroups.size) return;
  document.getElementById('reprocessModal').classList.add('show');
}

async function reprocessGroups() {
  const criteria = document.querySelector('input[name="criteria"]:checked').value;
  const indices = Array.from(selectedGroups);
  document.getElementById('reprocessModal').classList.remove('show');
  try {
    const resp = await fetch('/api/actions/reprocess', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({group_indices: indices, criteria: criteria})
    });
    const result = await resp.json();
    if (result.ok) {
      toast(`Reprocessed ${result.updated} group(s) — best photos updated`);
      selectedGroups.clear();
      document.getElementById('bulkBar').classList.remove('show');
      document.getElementById('bulkMerge').style.display = 'none';
      await load();
    } else {
      alert('Error: ' + (result.error || 'Unknown'));
    }
  } catch(e) { alert('Request failed: ' + e); }
}

/* Split: track photo checkbox selections in detail view */
function updateSplitBtn(groupIndex) {
  const checked = document.querySelectorAll('.photo-checkbox:checked');
  const bar = document.getElementById('splitBar');
  if (bar) {
    bar.classList.toggle('show', checked.length > 0);
    const countEl = document.getElementById('splitCount');
    if (countEl) countEl.textContent = checked.length + ' photo(s) selected to split';
  }
}

async function splitSelectedPhotos(groupIndex) {
  const selectedIds = Array.from(document.querySelectorAll('.photo-checkbox:checked'))
    .map(cb => cb.value);
  if (!selectedIds.length) return;
  if (!confirm(`Split ${selectedIds.length} photo(s) into a new group?`)) return;
  try {
    const resp = await fetch('/api/actions/split-group', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({group_index: groupIndex, photo_asset_ids: selectedIds})
    });
    const result = await resp.json();
    if (result.ok) {
      toast('Split complete — new group ' + result.new_group_index + ' created');
      document.getElementById('overlay').classList.remove('show');
      await load();
    } else {
      alert('Error: ' + (result.error || 'Unknown'));
    }
  } catch(e) { alert('Request failed: ' + e); }
}

document.getElementById('search').oninput = render;
document.getElementById('bulkMode').onchange = () => {
  if (!document.getElementById('bulkMode').checked) {
    selectedGroups.clear();
    document.getElementById('bulkBar').classList.remove('show');
    render();
  }
};

/* Tab switching */
function switchTab(tab) {
  document.getElementById('tabGroups').classList.toggle('active', tab === 'groups');
  document.getElementById('tabPeople').classList.toggle('active', tab === 'people');
  document.getElementById('groupsView').style.display = tab === 'groups' ? '' : 'none';
  document.getElementById('peopleView').style.display = tab === 'people' ? '' : 'none';
  if (tab === 'people') loadPeople();
}

/* People view */
let peopleCache = null;

async function loadPeople() {
  const grid = document.getElementById('peopleGrid');
  const photos = document.getElementById('personPhotos');
  photos.style.display = 'none';
  grid.style.display = '';

  if (!peopleCache) {
    grid.innerHTML = '<div style="padding:2rem;opacity:0.6">Loading people...</div>';
    try {
      const resp = await fetch('/api/people');
      peopleCache = await resp.json();
      if (peopleCache.error) {
        grid.innerHTML = `<div style="padding:2rem;color:var(--danger)">${peopleCache.error}</div>`;
        return;
      }
    } catch(e) {
      grid.innerHTML = `<div style="padding:2rem;color:var(--danger)">Failed to load people: ${e}</div>`;
      return;
    }
  }

  grid.innerHTML = '';
  peopleCache.forEach(p => {
    const card = document.createElement('div');
    card.className = 'person-card';
    card.onclick = () => showPersonPhotos(p);
    card.innerHTML = `
      <img src="/api/people/${p.id}/thumbnail" alt="${p.name}" loading="lazy">
      <div class="person-info">
        <div class="person-name">${p.name}</div>
        <div class="person-count">${p.assetCount} photo${p.assetCount !== 1 ? 's' : ''}</div>
      </div>`;
    grid.appendChild(card);
  });

  if (peopleCache.length === 0) {
    grid.innerHTML = '<div style="padding:2rem;opacity:0.6">No named people found in Immich</div>';
  }
}

async function showPersonPhotos(person) {
  const grid = document.getElementById('peopleGrid');
  const container = document.getElementById('personPhotos');
  grid.style.display = 'none';
  container.style.display = '';
  container.innerHTML = `
    <button class="back-btn" onclick="loadPeople()">Back to People</button>
    <h3>${person.name} (${person.assetCount} photos)</h3>
    <div style="padding:1rem 0;opacity:0.6">Loading photos...</div>`;

  try {
    const resp = await fetch('/api/people/' + person.id + '/photos');
    const photos = await resp.json();
    let photoGrid = '<div class="person-photo-grid">';
    photos.forEach(p => {
      photoGrid += `<img src="/api/thumbnail/${p.asset_id}" alt="${p.filename || ''}"
                        loading="lazy" onclick="openLightbox('${p.asset_id}', '${p.filename || p.id}')">`;
    });
    photoGrid += '</div>';
    container.innerHTML = `
      <button class="back-btn" onclick="loadPeople()">Back to People</button>
      <h3>${person.name} (${photos.length} photos loaded)</h3>
      ${photoGrid}`;
  } catch(e) {
    container.innerHTML = `
      <button class="back-btn" onclick="loadPeople()">Back to People</button>
      <div style="color:var(--danger)">Failed to load photos: ${e}</div>`;
  }
}

loadReportList();
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

        elif path == "/api/reports":
            self._handle_list_reports()

        elif path.startswith("/api/report/"):
            filename = path[len("/api/report/"):]
            self._handle_get_report(filename)

        elif path.startswith("/api/thumbnail/"):
            asset_id = path[len("/api/thumbnail/"):]
            self._proxy_image(asset_id, "thumbnail")

        elif path.startswith("/api/preview/"):
            asset_id = path[len("/api/preview/"):]
            self._proxy_image(asset_id, "preview")

        elif path.startswith("/api/full/"):
            asset_id = path[len("/api/full/"):]
            self._proxy_full(asset_id)

        elif path == "/api/people":
            self._handle_people()

        elif path.startswith("/api/people/") and path.endswith("/thumbnail"):
            person_id = path[len("/api/people/"):-len("/thumbnail")]
            self._handle_person_thumbnail(person_id)

        elif path.startswith("/api/people/") and path.endswith("/photos"):
            person_id = path[len("/api/people/"):-len("/photos")]
            self._handle_person_photos(person_id)

        else:
            self.send_error(404)

    def _proxy_image(self, asset_id, size):
        """Proxy an Immich thumbnail/preview, with fallback to local files."""
        data = None

        # Try Immich first
        if _immich_client:
            data = _immich_client.get_asset_thumbnail(asset_id, size=size)

        # Fall back to local file if available
        if not data:
            filepath = _get_local_filepath(asset_id)
            if filepath and Path(filepath).exists():
                max_size = 250 if size == 'thumbnail' else 1440
                data = _generate_thumbnail(filepath, max_size)

        if data:
            self._send_image(data)
        else:
            self.send_error(404, "Thumbnail not found")

    def _proxy_full(self, asset_id):
        """Proxy full-resolution download, with fallback to local files."""
        data = None

        # Try Immich first
        if _immich_client:
            data = _immich_client.download_asset(asset_id)

        # Fall back to local file if available
        if not data:
            filepath = _get_local_filepath(asset_id)
            if filepath and Path(filepath).exists():
                try:
                    data = Path(filepath).read_bytes()
                except Exception:
                    pass

        if data:
            # Detect content type from file extension
            content_type = "image/jpeg"
            filepath = _get_local_filepath(asset_id)
            if filepath:
                ext = Path(filepath).suffix.lower()
                content_types = {
                    '.png': 'image/png', '.gif': 'image/gif',
                    '.webp': 'image/webp', '.heic': 'image/heic',
                    '.mp4': 'video/mp4', '.mov': 'video/quicktime',
                }
                content_type = content_types.get(ext, 'image/jpeg')
            self._send_image(data, content_type=content_type)
        else:
            self.send_error(404, "Asset not found")

    def _handle_people(self):
        """Return list of named people from Immich."""
        if not _immich_client:
            self._send_json({"error": "No Immich client configured"}, 503)
            return
        people = _immich_client.get_people()
        # Filter to named people and format response
        result = []
        for p in people:
            name = p.get('name', '').strip()
            if not name:
                continue
            result.append({
                "id": p.get('id'),
                "name": name,
                "thumbnailPath": p.get('thumbnailPath', ''),
                "assetCount": p.get('assetCount', 0),
            })
        result.sort(key=lambda x: x['name'].lower())
        self._send_json(result)

    def _handle_person_thumbnail(self, person_id):
        """Proxy person face thumbnail from Immich."""
        if not _immich_client:
            self.send_error(503, "No Immich client configured")
            return
        data = _immich_client.get_person_thumbnail(person_id)
        if data:
            self._send_image(data)
        else:
            self.send_error(404, "Person thumbnail not found")

    def _handle_person_photos(self, person_id):
        """Return photo list for a specific person."""
        if not _immich_client:
            self._send_json({"error": "No Immich client configured"}, 503)
            return
        assets = _immich_client.get_person_assets(person_id, limit=200)
        result = []
        for a in assets:
            result.append({
                "id": a.id,
                "asset_id": a.id,
                "filename": a.original_file_name,
            })
        self._send_json(result)

    def _handle_list_reports(self):
        """List all report files in the reports directory."""
        reports = []
        report_dir = Path(_report_dir) if _report_dir else Path("reports")
        if report_dir.is_dir():
            for f in sorted(report_dir.glob("report_*.json"), reverse=True):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                    meta = data.get("metadata", {})
                    settings = data.get("settings", {})
                    reports.append({
                        "filename": f.name,
                        "generated_at": meta.get("generated_at", ""),
                        "total_groups": meta.get("total_groups", 0),
                        "total_photos": meta.get("total_photos", 0),
                        "settings_summary": {
                            "source_type": settings.get("source_type", ""),
                            "threshold": settings.get("similarity_threshold", ""),
                            "limit": settings.get("limit"),
                        },
                    })
                except Exception:
                    reports.append({"filename": f.name, "error": "Could not parse"})
        self._send_json(reports)

    def _handle_get_report(self, filename):
        """Serve a specific report file from the reports directory."""
        report_dir = Path(_report_dir) if _report_dir else Path("reports")
        report_file = report_dir / filename
        # Prevent path traversal
        try:
            report_file.resolve().relative_to(report_dir.resolve())
        except ValueError:
            self.send_error(403, "Forbidden")
            return
        if not report_file.exists():
            self.send_error(404, "Report not found")
            return
        try:
            with open(report_file) as f:
                data = json.load(f)
            self._send_json(data)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        if path == "/api/actions/set-best":
            self._handle_set_best(body)
        elif path == "/api/actions/bulk":
            self._handle_bulk(body)
        elif path == "/api/actions/merge-groups":
            self._handle_merge_groups(body)
        elif path == "/api/actions/split-group":
            self._handle_split_group(body)
        elif path == "/api/actions/reprocess":
            self._handle_reprocess(body)
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

    def _handle_merge_groups(self, body):
        """Merge multiple groups into the lowest-indexed one."""
        indices = set(body.get("group_indices", []))
        if len(indices) < 2:
            self._send_json({"ok": False, "error": "Need at least 2 groups to merge"}, 400)
            return

        report = _load_report()
        groups = report.get("groups", [])

        to_merge = [g for g in groups if g["group_index"] in indices]
        if len(to_merge) < 2:
            self._send_json({"ok": False, "error": "Groups not found"}, 404)
            return

        # Sort so we merge into the lowest-indexed group
        to_merge.sort(key=lambda g: g["group_index"])
        primary = to_merge[0]
        merged_index = primary["group_index"]

        # Combine all photos into primary; keep primary's current best
        current_best_id = primary["best_photo"]["asset_id"]
        all_photos = list(primary["photos"])
        merged_actions = set(primary["actions_taken"])
        for g in to_merge[1:]:
            for p in g["photos"]:
                p["is_best"] = False
                all_photos.append(p)
            merged_actions.update(g["actions_taken"])

        primary["photos"] = all_photos
        primary["photo_count"] = len(all_photos)
        primary["actions_taken"] = list(merged_actions)
        for p in primary["photos"]:
            p["is_best"] = (p["asset_id"] == current_best_id)

        # Remove the absorbed groups
        absorbed = {g["group_index"] for g in to_merge[1:]}
        report["groups"] = [g for g in groups if g["group_index"] not in absorbed]
        report.setdefault("metadata", {})["total_groups"] = len(report["groups"])

        _save_report(report)
        self._send_json({"ok": True, "merged_index": merged_index})

    def _handle_split_group(self, body):
        """Split selected photos out of a group into a new group."""
        group_index = body.get("group_index")
        split_ids = set(body.get("photo_asset_ids", []))

        if not split_ids:
            self._send_json({"ok": False, "error": "No photos selected to split"}, 400)
            return

        report = _load_report()
        groups = report.get("groups", [])

        source_group = next((g for g in groups if g["group_index"] == group_index), None)
        if not source_group:
            self._send_json({"ok": False, "error": "Group not found"}, 404)
            return

        remaining = [p for p in source_group["photos"] if p["asset_id"] not in split_ids]
        new_photos = [p for p in source_group["photos"] if p["asset_id"] in split_ids]

        if not remaining:
            self._send_json({"ok": False, "error": "Cannot split: group would become empty"}, 400)
            return
        if not new_photos:
            self._send_json({"ok": False, "error": "None of the specified photos found in group"}, 404)
            return

        # Update source group
        source_group["photos"] = remaining
        source_group["photo_count"] = len(remaining)
        orig_best_id = source_group["best_photo"]["asset_id"]
        if not any(p["asset_id"] == orig_best_id for p in remaining):
            # Original best was split away — pick first remaining as new best
            remaining[0]["is_best"] = True
            for p in remaining[1:]:
                p["is_best"] = False
            source_group["best_photo"] = {
                "id": remaining[0]["asset_id"],
                "asset_id": remaining[0]["asset_id"],
                "filename": remaining[0].get("filename", remaining[0]["asset_id"]),
            }

        # Create new group
        new_index = max(g["group_index"] for g in groups) + 1
        for p in new_photos:
            p["is_best"] = False
        new_photos[0]["is_best"] = True

        new_group = {
            "group_index": new_index,
            "photo_count": len(new_photos),
            "person_name": source_group.get("person_name"),
            "best_photo": {
                "id": new_photos[0]["asset_id"],
                "asset_id": new_photos[0]["asset_id"],
                "filename": new_photos[0].get("filename", new_photos[0]["asset_id"]),
            },
            "photos": new_photos,
            "actions_taken": [f"split_from_group_{group_index}"],
        }
        report["groups"].append(new_group)
        report.setdefault("metadata", {})["total_groups"] = len(report["groups"])

        _save_report(report)
        self._send_json({"ok": True, "new_group_index": new_index})

    def _handle_reprocess(self, body):
        """Re-pick the best photo in each selected group using a given criterion."""
        indices = set(body.get("group_indices", []))
        criteria = body.get("criteria", "filesize")
        updated = 0

        report = _load_report()

        for g in report.get("groups", []):
            if g["group_index"] not in indices:
                continue

            photos = g["photos"]
            if len(photos) < 2:
                continue

            best_photo = None
            if criteria == "filesize":
                def _size(p):
                    s = p.get("filesize") or p.get("exif_fileSizeInByte", "0")
                    try:
                        return float(str(s).replace(",", ""))
                    except (ValueError, TypeError):
                        return 0.0
                best_photo = max(photos, key=_size)

            elif criteria == "dimensions":
                def _pixels(p):
                    dim = p.get("dimensions", "0x0")
                    try:
                        w, h = str(dim).split("x")
                        return int(w) * int(h)
                    except (ValueError, AttributeError):
                        return 0
                best_photo = max(photos, key=_pixels)

            elif criteria == "date_oldest":
                def _date_asc(p):
                    return str(p.get("exif_dateTimeOriginal") or p.get("exif_DateTime") or "9999")
                best_photo = min(photos, key=_date_asc)

            elif criteria == "date_newest":
                def _date_desc(p):
                    return str(p.get("exif_dateTimeOriginal") or p.get("exif_DateTime") or "")
                best_photo = max(photos, key=_date_desc)

            if best_photo:
                new_best_id = best_photo["asset_id"]
                old_best_id = g.get("best_photo", {}).get("asset_id")
                for p in photos:
                    p["is_best"] = (p["asset_id"] == new_best_id)
                g["best_photo"] = {
                    "id": new_best_id,
                    "asset_id": new_best_id,
                    "filename": best_photo.get("filename", new_best_id),
                }
                # Update Immich favorites if client is available
                if _immich_client and old_best_id and old_best_id != new_best_id:
                    _immich_client.update_asset(old_best_id, is_favorite=False)
                    _immich_client.update_asset(new_best_id, is_favorite=True)
                updated += 1

        _save_report(report)
        self._send_json({"ok": True, "updated": updated})


def start_viewer_background(report_path, port=8080, immich_client=None, report_dir="reports"):
    """
    Start the web viewer server in a background daemon thread.

    Args:
        report_path: Path to the report JSON file
        port: HTTP port (default: 8080)
        immich_client: Optional ImmichClient for thumbnail proxying
        report_dir: Directory containing timestamped reports

    Returns:
        The background thread
    """
    import threading

    global _report_path, _immich_client, _report_dir
    _report_path = str(report_path)
    _immich_client = immich_client
    _report_dir = str(report_dir)

    # Build local file cache for fallback serving
    _build_local_file_cache()

    server = HTTPServer(("0.0.0.0", port), ViewerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def start_viewer(report_path, port=8080, immich_client=None, report_dir="reports"):
    """
    Start the web viewer server.

    Args:
        report_path: Path to processing_report.json
        port: HTTP port (default: 8080)
        immich_client: Optional ImmichClient for thumbnail proxying and actions
        report_dir: Directory containing timestamped reports (default: reports)
    """
    global _report_path, _immich_client, _report_dir
    _report_path = str(report_path)
    _immich_client = immich_client
    _report_dir = str(report_dir)

    if not os.path.exists(_report_path):
        print(f"Error: Report file not found: {_report_path}")
        print("Run the organizer first to generate a processing report.")
        sys.exit(1)

    # Build local file cache for fallback serving
    _build_local_file_cache()
    local_files_count = len(_local_file_cache)

    server = HTTPServer(("0.0.0.0", port), ViewerHandler)
    print(f"\nPhoto Organizer Viewer running at http://localhost:{port}")
    print(f"Report: {_report_path}")
    if _immich_client:
        print(f"Immich: {_immich_client.url} (thumbnails + full photos enabled)")
    elif local_files_count > 0:
        print(f"Local files: {local_files_count} photos with local paths (serving directly)")
    else:
        print("Note: No Immich client or local paths — thumbnails will not load")
    print("Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nViewer stopped.")
        server.server_close()
