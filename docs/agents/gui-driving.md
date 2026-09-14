# Driving the GUI

Cheapest option first. Stop at the first one that answers the question.

## 1. `pytest-qt` e2e tests (default, every OS)

`tests/e2e/` runs offscreen and has pixel snapshots. Any bug found by driving the GUI by hand gets pinned down as a test here. See `tests/conftest.py` for `--headed`, `--pause`, and `--update-snapshots`.

## 2. The harness's own computer use (macOS, Windows)

If the agent harness ships desktop control, use it instead of hand-rolled scripts. Launch labelme, then screenshot, click, and type through the harness tool.

- Claude Code: built-in `computer-use` MCP server. CLI on macOS; desktop app on macOS and Windows. Enable via `/mcp` in the CLI or the desktop app settings. Interactive sessions only. Docs: <https://code.claude.com/docs/en/computer-use>
- Codex: desktop app on macOS and Windows.

Neither supports Linux. This is the live desktop, so the window is visible to the user.

## 3. Xvfb sandbox (Linux)

Isolated X display: fixed geometry, no focus stealing, matches CI. Requires `Xvfb` (Arch: `xorg-server-xvfb`), `xdotool`, and ImageMagick.

```sh
Xvfb :99 -screen 0 1600x1000x24 &
export DISPLAY=:99
QT_QPA_PLATFORM=xcb .venv/bin/labelme examples/tutorial/apc2016_obj3.jpg &
WID=$(xdotool search --sync --onlyvisible --pid $! | tail -1)
xdotool windowsize "$WID" 1400 900
xdotool mousemove 60 200 click 1        # click by screen coordinate
xdotool key --window "$WID" ctrl+plus   # keyboard shortcut
import -window root /tmp/shot.png       # ImageMagick screenshot
```

Kill labelme and Xvfb when done. Coordinates depend on the window size, so set it before reading a screenshot. `xdotool` warns about `XGetInputFocus` because no window manager runs on the display; ignore it.

## 4. Live desktop by hand (harnesses without computer use)

The window takes focus from the user, so reserve this for when the user wants to watch, for PR screenshots, or for Wayland-only behavior.

### Linux

Same commands as tier 3 without `DISPLAY=:99`. On Wayland, labelme must still run with `QT_QPA_PLATFORM=xcb` so `xdotool` can reach it; use `grim` for full-screen captures. The compositor picks the window size.

### macOS

Everything needed ships with the OS. The terminal running the agent needs Accessibility permission for synthetic input and Screen Recording permission for captures.

```sh
.venv/bin/labelme examples/tutorial/apc2016_obj3.jpg &
osascript -e 'tell application "System Events" to tell process "labelme" to set {position, size} of front window to {{0, 0}, {1400, 900}}'
osascript -e 'tell application "System Events" to click at {60, 200}'
osascript -e 'tell application "System Events" to keystroke "+" using command down'
screencapture -x /tmp/shot.png
```

`screencapture` captures at Retina scale, so a 1400x900 window yields a 2800x1800 region; halve coordinates read from the image before clicking.
