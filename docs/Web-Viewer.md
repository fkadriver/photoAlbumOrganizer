# Web Interface Design

A modern web interface for reviewing and managing photo groups discovered by the Photo Album Organizer.

## Overview

The web interface provides an intuitive way to:
- Review photo groups before finalizing
- Select the best photo from each group
- Split or merge groups
- Apply changes back to source (local or Immich)
- View similarity scores and metadata

## Architecture

### Technology Stack

**Backend:**
- FastAPI (Python web framework)
- SQLite (group database)
- WebSockets (real-time updates)

**Frontend:**
- React (UI framework)
- TailwindCSS (styling)
- React Query (data fetching)
- Lightbox (photo viewing)

### Project Structure

```
photo_organizer/
├── cli.py              # Command-line interface (existing)
├── api/
│   ├── server.py       # FastAPI server
│   ├── routes.py       # API endpoints
│   ├── models.py       # Data models
│   └── database.py     # Database operations
├── web/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── GroupGrid.tsx
│   │   │   ├── GroupDetail.tsx
│   │   │   ├── PhotoCard.tsx
│   │   │   └── MetadataPanel.tsx
│   │   ├── hooks/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
└── database/
    └── groups.db       # SQLite database
```

## User Interface

### Main Views

#### 1. Dashboard View
```
┌─────────────────────────────────────────────────────┐
│  Photo Album Organizer                    [Settings]│
├─────────────────────────────────────────────────────┤
│                                                      │
│  📊 Summary                                          │
│  ├─ 127 groups found                                │
│  ├─ 342 total photos                                │
│  ├─ 89 groups reviewed                              │
│  └─ 38 groups remaining                             │
│                                                      │
│  🔍 Filters:  [All] [Reviewed] [Unreviewed]        │
│              [Has Faces] [No Faces]                 │
│              Similarity: ─────●─────                │
│                         (0)   (5)   (10)            │
│                                                      │
│  📁 Groups:                                          │
│  ┌──────────┬──────────┬──────────┬──────────┐     │
│  │  Group   │  Group   │  Group   │  Group   │     │
│  │  #001    │  #002    │  #003    │  #004    │     │
│  │  ⭐ Best │  ⚠️ Review│  ✓ Done  │  ⭐ Best │     │
│  │  5 photos│  3 photos│  7 photos│  4 photos│     │
│  └──────────┴──────────┴──────────┴──────────┘     │
│                                                      │
└─────────────────────────────────────────────────────┘
```

#### 2. Group Detail View
```
┌─────────────────────────────────────────────────────┐
│  ← Back to Groups              Group #001  [Actions▾]│
├─────────────────────────────────────────────────────┤
│                                                      │
│  Photos in this group (5 total)   Similarity: 3.2   │
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │  [⭐ BEST]         [Select]         [Select]   │ │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐ │ │
│  │  │           │  │           │  │           │ │ │
│  │  │   Photo   │  │   Photo   │  │   Photo   │ │ │
│  │  │     1     │  │     2     │  │     3     │ │ │
│  │  │           │  │           │  │           │ │ │
│  │  │  😊 😊    │  │  😐       │  │  😊       │ │ │
│  │  │  Score: 95│  │  Score: 72│  │  Score: 84│ │ │
│  │  └───────────┘  └───────────┘  └───────────┘ │ │
│  │                                                │ │
│  │  [Select]         [Select]                    │ │
│  │  ┌───────────┐  ┌───────────┐                │ │
│  │  │           │  │           │                │ │
│  │  │   Photo   │  │   Photo   │                │ │
│  │  │     4     │  │     5     │                │ │
│  │  │           │  │           │                │ │
│  │  │  😊       │  │  😐 😐    │                │ │
│  │  │  Score: 81│  │  Score: 65│                │ │
│  │  └───────────┘  └───────────┘                │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  Actions:                                            │
│  [✓ Mark as Reviewed] [Split Group] [Merge with...] │
│  [Remove Photo]       [Export Group]                │
│                                                      │
│  Metadata:                                           │
│  ├─ Taken: 2024-03-15 14:23:45                      │
│  ├─ Location: Family Park                           │
│  ├─ Camera: Canon EOS R5                            │
│  └─ Faces detected: 2                               │
│                                                      │
└─────────────────────────────────────────────────────┘
```

#### 3. Photo Comparison View
```
┌─────────────────────────────────────────────────────┐
│  ← Back to Group              Compare Photos         │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────────────────────┐  ┌──────────────────────┐ │
│  │                      │  │                      │ │
│  │                      │  │                      │ │
│  │      Photo 1         │  │      Photo 2         │ │
│  │    (Current Best)    │  │                      │ │
│  │                      │  │                      │ │
│  │                      │  │                      │ │
│  └──────────────────────┘  └──────────────────────┘ │
│                                                      │
│  Face Quality Scores:                                │
│  Photo 1: ████████░░ 85/100  (2 faces smiling)      │
│  Photo 2: ██████░░░░ 72/100  (1 face smiling)       │
│                                                      │
│  Image Quality:                                      │
│  Photo 1: Sharp, Well-exposed, Good lighting        │
│  Photo 2: Slightly soft, Overexposed highlights     │
│                                                      │
│  [← Previous] [Select Photo 1] [Select Photo 2] [Next →]│
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Features

#### Interactive Photo Selection
- Click any photo to make it "best"
- Drag and drop to reorder
- Side-by-side comparison mode
- Keyboard shortcuts (1-9 for selection, arrows for navigation)

#### Face Detection Visualization
```typescript
// Overlay faces with bounding boxes
interface FaceOverlay {
  x: number;
  y: number;
  width: number;
  height: number;
  smile_score: number;
  eyes_open: boolean;
  quality_score: number;
}

// Display on hover
<div className="face-indicator">
  <div className="face-box" style={facePosition}>
    <span className="face-score">😊 95</span>
  </div>
</div>
```

#### Metadata Panel
- EXIF data display
- GPS location (with map if available)
- Face detection results
- Similarity scores
- Edit history

#### Bulk Actions
- Select multiple groups
- Apply same action to all
- Batch mark as reviewed
- Batch export

## API Endpoints

### Groups
```
GET    /api/groups                  # List all groups
GET    /api/groups/{id}             # Get group details
PUT    /api/groups/{id}             # Update group
DELETE /api/groups/{id}             # Delete group
POST   /api/groups/{id}/split       # Split into multiple groups
POST   /api/groups/merge            # Merge groups
```

### Photos
```
GET    /api/photos/{id}             # Get photo details
GET    /api/photos/{id}/image       # Get image data
PUT    /api/photos/{id}/best        # Mark as best in group
GET    /api/photos/{id}/metadata    # Get full metadata
```

### Actions
```
POST   /api/apply                   # Apply all changes
POST   /api/export                  # Export results
GET    /api/status                  # Get processing status
```

### WebSocket
```
WS     /ws                          # Real-time updates
```

## Data Models

### Group Model
```python
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Group(BaseModel):
    id: int
    photos: List[Photo]
    best_photo_id: Optional[int]
    similarity_score: float
    reviewed: bool = False
    created_at: datetime
    updated_at: datetime
    metadata: dict = {}

class Photo(BaseModel):
    id: int
    group_id: int
    filename: str
    path: str
    hash: str
    thumbnail_url: str
    full_url: str
    face_count: int
    face_quality_score: float
    metadata: dict
    exif: dict
    is_best: bool = False
```

## Usage

### Starting the Web Server

```bash
# Start processing and web server
python ../src/photo_organizer.py \
  -s ~/Photos \
  -o ~/Organized \
  --web-ui \
  --port 8000

# Server starts at http://localhost:8000
# Processing happens in background
# Web UI updates in real-time
```

### Web-Only Mode

```bash
# Review previously processed groups
python ../src/photo_organizer.py \
  --web-only \
  --database groups.db \
  --port 8000
```

### Integration with Immich

```bash
# Process Immich photos with web review
python ../src/photo_organizer.py \
  --source immich \
  --web-ui \
  --port 8000

# After review, sync changes back to Immich
# Click "Apply to Immich" button in web UI
```

## Workflow

### Standard Workflow

1. **Initial Scan**
   ```bash
   python ../src/photo_organizer.py -s ~/Photos --web-ui
   ```

2. **Review in Browser**
   - Open http://localhost:8000
   - Review each group
   - Select best photos
   - Split/merge groups as needed
   - Mark groups as reviewed

3. **Apply Changes**
   - Click "Apply All Changes"
   - Confirms selections
   - Organizes files
   - Updates database

4. **Export Results**
   - Download organized photos
   - Export metadata
   - Generate report

### Advanced Workflow with Immich

1. **Scan Immich Library**
   ```bash
   python ../src/photo_organizer.py \
     --source immich \
     --web-ui \
     --tag-mode
   ```

2. **Review in Web UI**
   - See all potential duplicates
   - Compare photos side-by-side
   - Decide which to keep

3. **Apply to Immich**
   - Tag originals in Immich
   - Create albums for groups
   - Mark best photos as favorites
   - Option to archive/hide duplicates

## Real-Time Updates

### WebSocket Events

```typescript
// Client connects to WebSocket
const ws = new WebSocket('ws://localhost:8000/ws');

// Server sends updates
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  
  switch (update.type) {
    case 'group_processed':
      // New group found
      addGroup(update.group);
      break;
    
    case 'processing_progress':
      // Update progress bar
      setProgress(update.progress);
      break;
    
    case 'group_updated':
      // Group changed (by other user?)
      updateGroup(update.group);
      break;
  }
};
```

## Mobile Support

### Responsive Design
- Mobile-first approach
- Touch-friendly interactions
- Swipe gestures for navigation
- Native photo gestures (pinch zoom)

### Progressive Web App
- Offline capability
- Install as app
- Push notifications for completion
- Background sync

## Performance

### Optimization Strategies

1. **Lazy Loading**
   - Load thumbnails first
   - Load full images on demand
   - Virtual scrolling for large lists

2. **Caching**
   - Browser cache for thumbnails
   - IndexedDB for offline support
   - Service worker for PWA

3. **Image Optimization**
   - Generate multiple sizes
   - WebP format support
   - Progressive loading

4. **API Optimization**
   - Pagination (50 groups/page)
   - Request batching
   - Response compression

## Security

### Authentication
```python
# Optional authentication
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.get("/api/groups")
async def get_groups(credentials: HTTPBearer = Depends(security)):
    # Verify token
    if not verify_token(credentials.credentials):
        raise HTTPException(status_code=401)
    return groups
```

### Access Control
- Read-only mode for viewers
- Admin mode for changes
- API key support
- HTTPS recommended

## Future Enhancements

- [ ] **Collaborative Review**: Multiple users review simultaneously
- [ ] **ML Suggestions**: AI recommends best photo
- [ ] **Facial Recognition**: Group by person
- [ ] **Timeline View**: Organize by date/time
- [ ] **Map View**: Organize by GPS location
- [ ] **Duplicate Confidence**: Show % similarity
- [ ] **Undo/Redo**: Full history tracking
- [ ] **Export Formats**: Multiple export options
- [ ] **Plugin System**: Custom actions/filters
- [ ] **Mobile App**: Native iOS/Android apps

## See Also

- [API Documentation](API.md)
- [Development Guide](DEVELOPMENT.md)
- [Immich Integration](Immich.md)
