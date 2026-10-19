# activity-renew

Moves the mouse by 1 pixel and back when there has been no input for a while,
so the session is not considered idle.

The tkinter window lets you set the interval, start and stop the simulation,
pick a mode, switch the interface language (English or Russian) and watch the
event log. **Help → About** shows the version and a short description in a
dialog centered over the main window.

## Why this is not just XTest

The obvious approach — `xdotool`, `pynput` or `pyautogui` — **does not work on
Wayland**. They move the cursor, but they do not reset Mutter's idle counter.
This was verified on a clean session: idle time kept growing from 4694 ms to
5785 ms across synthetic movements, so the session still considered itself
idle.

That is why there are two other mechanisms:

- **`uinput`** — creates a real virtual input device through `/dev/uinput`.
  The compositor sees it as hardware, so the event counts for both the
  operating system and applications. The cursor actually moves one pixel and
  comes back.
- **`inhibit`** — asks the session not to go idle through D-Bus
  (`org.gnome.SessionManager.Inhibit`, flag 8 = idle). The mouse does not move
  at all, and no permission setup is needed.

Idle time comes from `org.gnome.Mutter.IdleMonitor`. In a Wayland session this
is the only authoritative source: the XScreenSaver extension is unavailable,
and global input hooks are impossible by design.

## Installation

Three options, from most convenient to least. Both artifacts and
`SHA256SUMS` are attached to GitHub Releases and built automatically when a
release is published (`.github/workflows/release.yml`).

**.deb package** (Ubuntu/Debian). It pulls in the dependencies and installs the
`/dev/uinput` access rule itself, so the `uinput` mode works right away with no
manual steps:

```bash
sudo apt install ./activity-renew_0.2.0_all.deb
activity-renew
```

**Standalone binary.** A single file with Python and the libraries inside. The
remaining dependencies are `xdotool` and the udev rule (see below):

```bash
chmod +x activity-renew
./activity-renew
```

**From source.** If you want to modify the code:

```bash
git clone https://github.com/PavlenkoEvgeniy/python-activity-renew.git
cd python-activity-renew
python3 -m activity_renew
```

## Requirements

A GNOME session (Wayland or X11). Everything needed is already in the system;
nothing has to be installed from pip:

| What | Why | Package |
|---|---|---|
| Python 3 | | `python3` |
| tkinter | window | `python3-tk` |
| dbus-python | idle time, lock state, inhibit | `python3-dbus` |
| evdev | virtual mouse | `python3-evdev` |
| xdotool | cursor position and screen size | `xdotool` |

## One-time setup for `uinput` mode

**If you installed the .deb, skip this section**: the rule is already installed
and applied by the package.

The virtual mouse is always created, but its `/dev/input/eventN` node gets
`root:input` permissions without an ACL. The compositor does not read such a
device, and the events go nowhere. Grant access once:

```bash
sudo tee /etc/udev/rules.d/99-activity-renew.rules >/dev/null <<'EOF'
KERNEL=="event*", SUBSYSTEM=="input", ATTRS{name}=="activity-renew*", TAG+="uaccess"
EOF
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=input
```

The rule matches the device name, so access to real keyboards and mice is not
widened (unlike adding the user to the `input` group).

Check the result:

```bash
python3 -m activity_renew --check
```

The command moves the cursor 25 px and back. If it does not move, you will see
exactly that reason instead of a silent “seems to work”.

## Running

```bash
cd /path/to/python-activity-renew
python3 -m activity_renew
```

Only one copy can run at a time: the second one shows “Already running” and
exits. The lock is a `flock` in `$XDG_RUNTIME_DIR`; the kernel releases it, so
there is nothing to clean up.

## Modes

| Mode | What it does | When to use it |
|---|---|---|
| `uinput` (default) | moves the mouse 1 px and back | the usual case: real input events are needed |
| `inhibit` | holds an idle inhibit continuously | enough to keep the screen from blanking or locking |
| `both` | both at once | belt and braces: inhibit for the OS, mouse movement for applications |

In `inhibit` mode the interval field is disabled: the screen never blanks, so
idle time does not affect anything.

## Interface language

The interface is in English by default. Pick **Русский** in the **Language**
box to switch to Russian; the change applies immediately and is stored in the
configuration file. The About dialog and all status and log messages follow the
selected language.

## Settings

The file is `~/.config/activity-renew/config.json` and is created on the first
change. Edits apply on the fly. Unknown keys are preserved, so the file is safe
to edit by hand.

| Key | Default | Meaning |
|---|---|---|
| `language` | `"en"` | interface language: `en` or `ru` |
| `interval_seconds` | `120` | idle time after which to jiggle (5…86400) |
| `mode` | `"uinput"` | `uinput`, `inhibit` or `both` |
| `pause_when_locked` | `true` | pause while the screen is locked |
| `jiggle_hold_ms` | `60` | delay between moving away and back, ms |
| `log_limit` | `20` | how many events to keep in the log |

Out-of-range values are clamped, and a note appears in the window log.

## Autostart at login

`~/.config/autostart/activity-renew.desktop` (use your own path):

```ini
[Desktop Entry]
Type=Application
Name=activity-renew
Comment=Moves the mouse so the session is not considered idle
Exec=python3 -m activity_renew
Path=/home/p3s/Projects/my/python-activity-renew
Terminal=false
X-GNOME-Autostart-enabled=true
```

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

The tests cover pure logic: the “time to jiggle” decision on a fake clock,
configuration parsing and validation, and interface translations. The GUI,
D-Bus and evdev are not covered by tests; `--check` verifies them on a live
session.

## Known limitations

- **GNOME only.** The idle source is Mutter; on KDE, Sway and others the desktop
  integration will not work, and the application refuses to start with a clear
  message.
- **Drift at the screen edge.** The cursor position is read through the
  XWayland mirror (`xdotool`). If `xdotool` is not installed, the direction is
  chosen at random, and right at the screen edge a jiggle can move the cursor
  by one pixel.
- **End-to-end `uinput` verification is incomplete.** The mechanism has not
  been fully confirmed: when this was written the udev rule had not been
  installed yet, so resetting the idle counter with a real virtual mouse was
  not proven — only that XTest does not reset it. After installing the rule,
  run `--check`.
- **The application does not start itself** after a reboot: use the autostart
  recipe above.
