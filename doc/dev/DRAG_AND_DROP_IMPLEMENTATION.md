# Drag-and-Drop Implementation Guide

> **Note.** The backend-layer specifics below — the platform backend base class,
> the CoreGraphics renderer, and the "add a new platform backend" walkthrough —
> live in the external **[PuiKit](https://github.com/crftwr/puikit)** framework
> (`../puikit`; see its `docs/drag_drop.md` and `puikit/backends/`), where the
> APIs differ from what is sketched here. XeFM's application-layer
> drag-initiation design still applies.

## Overview

This document provides comprehensive implementation details for XeFM's drag-and-drop feature, which enables users to drag files from the file manager to external applications on desktop platforms, and to drop files onto a pane from other applications or the other pane. The implementation is designed with a platform-agnostic architecture at the XeFM level, with platform-specific implementations in the PuiKit backend layer.

**Target Audience**: Developers working on XeFM, contributors adding platform support, maintainers debugging drag-and-drop issues.

**Current Platform Support**:
- ✅ macOS and Windows desktop app (drag out and drop in)
- ❌ Terminal mode — a drag-out copies the paths to the clipboard instead; no drop-in

## Architecture Overview

### Layered Design

The drag-and-drop implementation follows a four-layer architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    Layer 1: XeFM Application             │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Drag Gesture Detector                    │  │
│  │  - Tracks mouse button state                     │  │
│  │  - Calculates movement distance                  │  │
│  │  - Distinguishes click from drag                 │  │
│  └──────────────────────┬───────────────────────────┘  │
│                         │                               │
│  ┌──────────────────────┴───────────────────────────┐  │
│  │         Drag Payload Builder                     │  │
│  │  - Collects selected files or focused item       │  │
│  │  - Converts to absolute file:// URLs             │  │
│  │  - Validates file existence                      │  │
│  │  - Filters out remote/archive files              │  │
│  └──────────────────────┬───────────────────────────┘  │
│                         │                               │
│  ┌──────────────────────┴───────────────────────────┐  │
│  │         Drag Session Manager                     │  │
│  │  - Manages drag lifecycle                        │  │
│  │  - Coordinates with backend                      │  │
│  │  - Handles completion/cancellation               │  │
│  └──────────────────────┬───────────────────────────┘  │
└─────────────────────────┼────────────────────────────────┘
                          │
┌─────────────────────────┼────────────────────────────────┐
│            Layer 2: PuiKit Backend Interface             │
│  - Platform-agnostic API                                │
│  - Capability detection                                 │
│  - Callback registration                                │
└─────────────────────────┼────────────────────────────────┘
                          │
┌─────────────────────────┼────────────────────────────────┐
│         Layer 3: Platform-Specific Backend              │
│  ┌──────────────────────┴───────────────────────────┐  │
│  │      macOS Backend                               │  │
│  │  - Initiates native drag session                 │  │
│  │  - Provides file URLs to Pasteboard              │  │
│  │  - Handles drag image creation                   │  │
│  │  - Notifies completion                           │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────┼────────────────────────────────┘
                          │
┌─────────────────────────┼────────────────────────────────┐
│           Layer 4: Operating System                     │
│  - Native drag-and-drop system                          │
│  - Drag UI and cursor management                        │
│  - Drop target routing                                  │
│  - File operation execution                             │
└─────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Platform Independence**: XeFM code is platform-agnostic; platform-specific logic lives in backends
2. **Capability Detection**: Backends advertise drag-and-drop support via `supports_drag_and_drop()`
3. **Graceful Degradation**: Terminal mode returns False without errors
4. **Standard Protocols**: Uses file:// URLs (RFC 8089) for cross-platform compatibility
5. **Clean Separation**: Gesture detection, payload building, and session management are independent modules

## Component Details

### 1. Drag Gesture Detection

**Module**: `PuiKit`

**Purpose**: Detects drag gestures from mouse events and distinguishes them from clicks.

**Algorithm**:

```
1. Mouse Button Down:
   - Record start position (x, y)
   - Record start timestamp
   - Set button_down = True
   - Set dragging = False

2. Mouse Move (while button down):
   - Calculate distance from start: sqrt((x - start_x)² + (y - start_y)²)
   - If distance >= DRAG_DISTANCE_THRESHOLD (5 pixels):
     - Set dragging = True
     - Return True (drag detected)
   - Else:
     - Return False (still potential click)

3. Mouse Button Up:
   - If dragging == True:
     - Was a drag gesture
   - Else:
     - Was a click
   - Reset state
```

**Key Constants**:
- `DRAG_DISTANCE_THRESHOLD = 5` pixels - Minimum movement to trigger drag
- `DRAG_TIME_THRESHOLD = 0.15` seconds - Time window for gesture detection

**State Tracking**:
```python
@dataclass
class DragGestureState:
    button_down: bool = False      # Is mouse button currently pressed?
    start_x: int = 0                # Initial mouse X position
    start_y: int = 0                # Initial mouse Y position
    start_time: float = 0.0         # Timestamp of button down
    current_x: int = 0              # Current mouse X position
    current_y: int = 0              # Current mouse Y position
    dragging: bool = False          # Has drag threshold been exceeded?
```

**Implementation Notes**:
- Uses Euclidean distance for accurate threshold detection
- Threshold prevents accidental drags from small hand movements
- Time threshold (currently unused) reserved for future gesture refinement
- State resets on button up to prepare for next gesture

### 2. Drag Payload Building

**Module**: `PuiKit`

**Purpose**: Prepares file paths for drag operations, validates files, and converts to file:// URLs.

**Payload Selection Logic**:

```
IF selected_files is not empty:
    files_to_drag = selected_files
ELSE IF focused_item exists:
    IF focused_item == "..":
        RETURN None (cannot drag parent directory marker)
    files_to_drag = [focused_item]
ELSE:
    RETURN None (nothing to drag)
```

**Validation Pipeline**:

For each file in files_to_drag:
1. **File Count Check**: Reject if > 1000 files
2. **Remote File Check**: Reject if path starts with `s3://` or `ssh://`
3. **Archive Content Check**: Reject if path contains `::archive::`, `.zip/`, or `.tar/`
4. **Existence Check**: Reject if file does not exist on filesystem
5. **URL Conversion**: Convert to absolute file:// URL with proper encoding

**URL Conversion**:

```python
def _path_to_file_url(self, path: Path) -> str:
    """Convert file path to file:// URL following RFC 8089."""
    # 1. Resolve to absolute path
    absolute_path = path.resolve()
    
    # 2. Convert to POSIX format (forward slashes)
    posix_path = absolute_path.as_posix()
    
    # 3. URL-encode special characters (preserve forward slashes)
    encoded_path = quote(posix_path, safe='/')
    
    # 4. Prepend file:// scheme
    return f"file://{encoded_path}"
```

**Examples**:
- `/Users/john/file.txt` → `file:///Users/john/file.txt`
- `/Users/john/My Documents/file.txt` → `file:///Users/john/My%20Documents/file.txt`
- `/Users/john/file (copy).txt` → `file:///Users/john/file%20%28copy%29.txt`

**Implementation Notes**:
- MAX_FILES = 1000 to prevent performance issues with large selections
- Archive detection uses string markers (future: use Path metadata)
- Remote file detection is simple prefix check (future: use Path protocol)
- URL encoding handles spaces, parentheses, and other special characters

### 3. Drag Session Management

**Module**: `PuiKit`

**Purpose**: Manages the lifecycle of a drag-and-drop session from initiation to completion.

**State Machine**:

```
     start_drag()
IDLE ───────────────> DRAGGING
                         │
                         │ OS completes drag
                         ├──────────────────> COMPLETED
                         │                        │
                         │ OS cancels drag        │
                         └──────────────────> CANCELLED
                                                  │
                         ┌────────────────────────┘
                         │ _cleanup()
                         ▼
                       IDLE
```

**State Transitions**:
- `IDLE → DRAGGING`: Via `start_drag()` when backend accepts drag
- `DRAGGING → COMPLETED`: Via `handle_drag_completed()` when OS reports successful drop
- `DRAGGING → CANCELLED`: Via `handle_drag_cancelled()` when OS reports cancellation
- `COMPLETED/CANCELLED → IDLE`: Automatic via `_cleanup()`

**Resource Management**:

```python
def _cleanup(self) -> None:
    """Clean up drag session resources."""
    self.current_urls = None           # Release file URL list
    self.completion_callback = None    # Release callback reference
    self.state = DragState.IDLE        # Return to idle state
```

**Callback Protocol**:
- Completion callback receives boolean parameter: `callback(completed: bool)`
- `completed=True`: Drag completed successfully (dropped on valid target)
- `completed=False`: Drag was cancelled (Escape key, invalid target, etc.)
- Callback invoked before cleanup to allow state inspection

**Implementation Notes**:
- Only one drag session can be active at a time
- Attempting to start drag while DRAGGING returns False
- Backend must support drag-and-drop (checked via `supports_drag_and_drop()`)
- Cleanup is automatic and guaranteed after completion/cancellation

### 4. Backend Interface

The drag *source* itself is PuiKit's, not XeFM's. XeFM issues one intent —
`panel.begin_file_drag(paths, event, operations=..., on_complete=...)` — and
PuiKit resolves it per backend: a real OS drag session where the
`os_drag_drop` capability is present, and a clipboard fallback everywhere else
(notably the TUI, which cannot be an OS drag source at all).

The interface, its capability gating, the per-platform implementations and the
"add a new platform backend" walkthrough all live in the PuiKit repo — see its
`docs/drag_drop.md` and `puikit/backends/`. XeFM never branches on the backend,
so nothing below depends on which one is active.

### 5. The press the gesture starts on (issue #431)

A drag has no separate "begin" event: it begins on a press that later travels
far enough. So the press has to arrive, and on macOS the press that brings an
application forward does not — AppKit spends it on activation unless the view
answers `acceptsFirstMouse:` with YES. The symptom is precise: with XeFM in the
background, the first press-and-drag on a row did nothing at all (`FilePane`
never saw the `MOUSE_DOWN`, so `_press_index` stayed `-1` and no `MOUSE_DRAG`
crossed the threshold); the user let go, pressed again, and only that second
gesture dragged.

That answer belongs to the window, not to a widget, so it is a `WindowStyle`
axis in PuiKit — `takes_first_click` (puikit `docs/window_management.md`) — and
XeFM asks for it where it builds the GUI backend in `main()`:

```python
backend_kwargs["style"] = WindowStyle(takes_first_click=True)
```

Nothing else about the window changes, and the terminal backend is handed no
style at all. The cost is Finder's: the activating click now also lands on the
row it is over, moving the cursor there as it raises the window. Windows already
delivered that click (`DefWindowProc` answers `WM_MOUSEACTIVATE` with
`MA_ACTIVATE`), so the field changes nothing there.

## XeFM Integration

**Modules**: `xefm/file_pane.py` (gesture), `xefm/app.py` (what to drag, where a drop goes)

None of the `DragGestureDetector` / `DragPayloadBuilder` / `DragSessionManager`
objects sketched in sections 1–3 exist in XeFM. The XeFM side is a pair of
`FilePane` callbacks and the `XeFMApp` methods they call:

1. **Gesture** — `FilePane.handle_event` arms a possible drag on a left
   `MOUSE_DOWN` over a row (`_press_index`, `_press_xy`) without consuming it,
   so the Panel still synthesizes the click on release. On `MOUSE_DRAG`, once
   the Manhattan distance from the press reaches `DRAG_THRESHOLD` (1.5 base
   units, in `xefm/file_pane.py`), it calls `on_drag(index, event)` exactly once;
   the native session then owns the mouse. A press on the scrollbar or on empty
   space below the rows never drags.

2. **Wiring** — `XeFMApp` builds each pane with
   `on_drag=lambda i, ev: self._start_drag(side, i, ev)`,
   `on_drop=... self._on_drop(side, i, paths, op)` and
   `on_drop_query=... self._drop_effect(side, i, paths, op)`.

3. **Drag-out** — `_start_drag(pane_name, index, event)` takes the dragged row,
   or the whole marked set (in list order) when the row is marked, keeps only
   local paths (`_is_local`, i.e. not a `path_schemes` URI — so no `s3://`,
   `ssh://` or `archive://` entries), and calls
   `panel.begin_file_drag(paths, event=event, operations=("copy", "move"), on_complete=...)`.
   It records `_drag_source_pane` *before* starting, because the TUI clipboard
   fallback fires `on_complete` synchronously.
   `_on_drag_complete(paths, operation)` logs the outcome, relists both panes
   when the receiver reports `move`, and stays silent for a drag released in
   place (#230).

4. **Drop-in** — `FilePane` maps `FILE_DROP` (and `FILE_DRAG_OVER`) to the row
   under the pointer (`-1` below the last row). `_drop_plan()` decides the
   outcome once, for both the hover badge (`_drop_effect` → `"copy"` /
   `"move"` / `"none"`) and the drop itself (`_on_drop`):
   - refuse a search-results (virtual) pane or a browsed archive;
   - target the folder row under the drop, otherwise the pane's directory;
   - skip sources already in the destination — all skipped on the drag's own
     source pane is `in_place` (cancelled silently), elsewhere a refusal;
   - refuse `link`;
   - with no modifier, move when `_same_volume()` says every source shares the
     destination's volume, copy otherwise (#589).

   `_on_drop` then runs the shared copy/move engine (`self._fileops.copy` /
   `.move`) with its confirmation and conflict handling, and relists both panes
   on completion.

## Error Handling

### Error Categories

1. **Validation Errors** (Payload Building):
   - Remote files (S3, SSH)
   - Archive contents
   - Parent directory marker
   - Missing files
   - Too many files (> 1000)

2. **Backend Errors** (Session Management):
   - Backend doesn't support drag-and-drop
   - Native drag session fails to start
   - OS rejects drag operation

3. **State Errors** (Session Management):
   - Attempting to start drag while already dragging
   - Callback exceptions during completion

### Error Handling Strategy

**Validation Errors**:
- Return `None` from `build_payload()`
- Log appropriate message (info or error level)
- Optional user-visible error message
- No state changes required

**Backend Errors**:
- Return `False` from `start_drag()` or `start_drag_session()`
- Log error message
- Reset gesture detector
- Return to IDLE state

**State Errors**:
- Log warning message
- Continue with cleanup
- Ensure state returns to IDLE

### Error Recovery

All error paths ensure:
1. State returns to IDLE
2. Resources are cleaned up
3. Gesture detector is reset
4. UI can continue normal operation

## Testing Strategy

### Automated Tests

**Location**: `test/test_drag_and_drop.py`, driven headlessly (no window):

- `FilePaneGesture` — a press that travels past `DRAG_THRESHOLD` fires
  `on_drag` once; a press on empty space never drags; `FILE_DROP` reports the
  paths and the row (or `-1` below the rows).
- `AppDragDrop` — `_start_drag` hands the row, or the whole selection, to
  `panel.begin_file_drag`; `_on_drop` copies into the pane directory or a
  folder row, skips sources already there, cancels a drop back onto its source
  pane silently, still copies into a subfolder of the source pane, and refuses
  a virtual pane; `_on_drag_complete` clears the source pane.
- `InactiveWindowStartsADrag` — the GUI window is created with
  `WindowStyle(takes_first_click=True)` and nothing else changed; the terminal
  backend gets no style (#431).

The drag source and its per-backend behaviour are tested in PuiKit.

### Manual Testing

Required for:
- Visual verification of drag image
- Real drag-and-drop to external applications
- Drag cursor feedback
- Multi-file drag with large selections
- Edge cases with invalid drop targets

**Test Procedure**:
1. Select files in XeFM
2. Click and drag files
3. Drop on Finder, text editor, or other app
4. Verify files appear in target application

## Debugging

### Common Issues

**Issue**: Drag doesn't start
- Check `supports_drag_and_drop()` returns True
- Check payload builder returns non-None URLs
- Check backend logs for errors
- Verify mouse events are being received

**Issue**: Drag starts but immediately cancels
- Check OS drag system accepts file URLs
- Verify file paths are absolute
- Check file permissions
- Verify files exist on filesystem

**Issue**: Drag image doesn't appear
- Check drag_image_text is non-empty
- Verify backend creates drag image
- Check platform-specific image creation code

**Issue**: Completion callback not called
- Verify backend registers callback
- Check native code calls Python callback
- Verify callback doesn't raise exceptions

### Logging

Enable debug logging to trace drag operations:

```python
import logging
logging.getLogger("DragGesture").setLevel(logging.DEBUG)
logging.getLogger("DragPayload").setLevel(logging.DEBUG)
logging.getLogger("DragSession").setLevel(logging.DEBUG)
```

Key log messages:
- "Drag gesture detected" - Threshold exceeded
- "Built drag payload with N files" - Payload created
- "Started drag session with N files" - Backend accepted drag
- "Drag session completed" - OS reported success
- "Drag session cancelled" - OS reported cancellation

### Testing Checklist

Before releasing platform support:

- [ ] Unit tests pass for all components
- [ ] Property-based tests pass (100+ iterations)
- [ ] Integration tests pass
- [ ] Manual testing with real applications
- [ ] Drag single file works
- [ ] Drag multiple files works
- [ ] Drag image appears correctly
- [ ] Completion callback invoked
- [ ] Cancellation callback invoked
- [ ] Error cases handled gracefully
- [ ] Remote files rejected
- [ ] Archive contents rejected
- [ ] Parent directory marker rejected
- [ ] Large selections (100+ files) work
- [ ] File count limit (1000) enforced
- [ ] Special characters in filenames work
- [ ] Spaces in filenames work
- [ ] Unicode filenames work

## Performance Considerations

### Payload Building

- **File Count Limit**: 1000 files maximum to prevent UI freezing
- **Existence Checks**: O(n) file system calls - consider caching for large selections
- **URL Encoding**: O(n) string operations - minimal overhead

### Drag Session

- **State Tracking**: O(1) state machine operations
- **Callback Invocation**: O(1) function call
- **Resource Cleanup**: O(1) reference clearing

### Backend Integration

- **macOS**: Native drag session is asynchronous - no blocking
- **Windows**: DoDragDrop() blocks until drag completes - run in thread if needed
- **Linux**: Drag protocols are asynchronous - no blocking

### Optimization Opportunities

1. **Lazy URL Conversion**: Convert URLs only when drag starts (not during selection)
2. **Cached Validation**: Cache file existence checks for current directory
3. **Batch Operations**: Group file system operations when possible
4. **Async Callbacks**: Ensure callbacks don't block UI thread

## Security Considerations

### File Access

- **Validation**: All files validated before drag starts
- **Absolute Paths**: Only absolute paths allowed (no relative paths)
- **Existence Check**: Files must exist on filesystem
- **No Symlink Following**: Use resolved paths to prevent symlink attacks

### URL Encoding

- **Proper Encoding**: All special characters URL-encoded
- **No Injection**: URL encoding prevents path injection attacks
- **Standard Format**: RFC 8089 compliance ensures compatibility

### Platform Security

- **macOS**: Sandbox restrictions apply to dragged files
- **Windows**: UAC restrictions apply to drop targets
- **Linux**: File permissions enforced by OS

## References

### Standards

- [RFC 8089: The "file" URI Scheme](https://tools.ietf.org/html/rfc8089)
- [XDnD Protocol Specification](https://www.freedesktop.org/wiki/Specifications/XDND/)
- [Wayland Data Device Protocol](https://wayland.freedesktop.org/docs/html/apa.html#protocol-spec-wl_data_device)

### Platform Documentation

- [macOS Drag and Drop Programming Topics](https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/DragandDrop/DragandDrop.html)
- [Windows Drag-Drop Reference](https://docs.microsoft.com/en-us/windows/win32/shell/dragdrop)
- [Linux Drag and Drop](https://www.freedesktop.org/wiki/Specifications/)

### Related XeFM Documentation

- `doc/MOUSE_EVENT_SUPPORT_FEATURE.md` - End-user documentation (Dragging files section)
- `doc/dev/MOUSE_OPERATION_IMPLEMENTATION.md` - Mouse handling in the file panes

## Changelog

### Version 1.0 (Initial Implementation)

- macOS support via CoreGraphics backend
- Drag gesture detection with 5-pixel threshold
- Payload building with validation
- Session lifecycle management
- Error handling for common cases
- Unit and property-based tests
- Demo script and documentation

### Future Enhancements

- Linux X11 backend implementation
- Linux Wayland backend implementation
- Drag preview customization
- Progress feedback for large file operations
