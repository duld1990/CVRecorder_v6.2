# CVRecorder_v6.2
Small animal locomotion recorder for open-field tests, supporting up to 4 webcams with independent video settings.

v6.2 COMPACT LABELS AND SOURCE CHECKS
Existing v6/v6.1: close the app, replace recorder.py, then run the existing
02_start_recorder.bat. No new dependencies or internet access are required.
Source label example: 0 | C920 | READY. Full names and paths are in Details.
READY: source opened and a frame was read during the scan.
NO FRAME: source opened but no frame was obtained.
UNAVAILABLE: open failed or an error occurred; it may be busy/disconnected.
TIMEOUT: check exceeded its time limit (about 5 seconds per source).
UNCHECKED: unverified candidate index, not a claim that a device is connected.
Refresh briefly opens each named source, one at a time, using its default mode.
The camera LED may flash. The GUI remains responsive and selecting a source
cancels the remaining scan. Default-mode checks do not guarantee that custom
resolution/FPS/input-format settings are supported. Live preview verifies the
selected capture settings. A badge shows CONNECTING, CONNECTED, or NO SIGNAL.
READY is a scan-time result; refresh after reconnecting devices. Neither READY
nor CONNECTED detects a covered lens, black frames, or OBS placeholder content.
Buttons: Refresh, Index list, Disconnect, Start, Stop, Apply, Details, Browse.
Stop finishes recording and leaves preview running. No GUI text is saved in
video. Passed simulated label, source-check, fallback and four-channel tests;
Windows camera probing and rendering still require target-computer testing.

v6.2 SOURCE LIST RECOVERY
Close the app and replace recorder.py in your existing v6 installation. No
new dependencies are required. Then run 02_start_recorder.bat.
Refresh and scan status are now pinned at the top of the window.
The app initializes COM in camera-related Windows subprocesses. If device
name enumeration fails, returns zero devices, crashes, or times out, the
selectors retain UNVERIFIED indices 0-15. These are candidates, not detected
cameras. Select an index to attempt preview, and verify which lens it uses.
The index-list button bypasses name enumeration. Selecting a candidate during
a name scan cancels that scan. Disconnect before changing backend.
Unknown index entries cannot identify virtual cameras; inspect the preview.
The exact cause of the reported empty list is not confirmed without the
target-computer error. This patch provides error visibility and a fallback.

FOUR-CHANNEL WEBCAM RECORDER v6.2 - WINDOWS x64 OFFLINE

NEW IN v6.2
- Four channels in a scrollable 2x2 layout. Use the vertical scrollbar on
  smaller screens. Each channel has independent requested video parameters.
- Resolution presets: 640x480, 800x600, 1280x720, 1920x1080; custom even
  WidthxHeight can be typed. FPS presets: 5,10,15,20,25,30,60; custom positive
  FPS can be typed. These are requests, not an enumeration of supported modes.
- Input choices: AUTO (driver default), MJPG, YUY2. This is camera/USB
  transport format, independent of output MP4/AVI encoding.
- Actual resolution, driver-reported FPS/FourCC, measured acquisition FPS,
  rejected settings, and resolution/FPS substitution warnings are displayed
  or logged. Drivers may ignore settings even if a set call returns success.
- Real device names, OpenCV indices, backend, and device-path short tags.
- Identical camera models remain distinguishable by index and device-path tag.
- Names containing OBS, Virtual, ManyCam, or Snap Camera show [VIRTUAL?].
  This is a name-based warning, not a complete physical-device classifier.
- Select a source to connect and start live preview immediately, without saving.
- Start recording uses the same open camera connection. Stop keeps preview alive.
- Each slot has optional Camera# and ID# fields and a filename preview.

INSTALL / UPDATE WITHOUT INTERNET
First installation:
1. Extract the entire package to a writable folder, e.g. C:\BehaviorRecorder.
2. Run 01_install_offline.bat. No Anaconda or internet is needed.
3. Run 02_start_recorder.bat.

Existing bundled installation:
1. Close the recorder. Extract the v6 update into the existing installation
   folder, merging the wheels folder and replacing the supplied script files.
   Keep the existing runtime folder.
2. Run 00_update_offline.bat. This installs the new named-device enumeration
   dependency from the included Windows wheel, without internet access.
3. Run 02_start_recorder.bat.

v6 uses the same dependencies as v5. Older installations need the included
named-device enumeration dependency; use the update script for either case. Python 3.11 x64 is required for these bundled wheels.
For a custom Python 3.11 x64 environment, activate it and run
03_install_into_existing_python.bat, then python recorder.py.

Included: Python 3.11.9 x64 full installer (pip and Tk), OpenCV 4.10.0.84,
NumPy 1.26.4, Pillow 11.1.0, cv2-enumerate-cameras 1.2.2, and VC++ runtime.
The Python installer is a full offline installer, not the latest Python
security release. If cv2 import fails with a DLL error, install
vc_redist.x64.exe; IT/admin support may be needed. Windows N/KN may require
additional offline Windows media components that are not included.
Do not install inside the ZIP, in Program Files, or a read-only directory.
Do not move an installed runtime folder. Keep at least 2 GB for installation
and sufficient separate space for recordings.

IDENTIFY SOURCES AND PREVIEW
1. Close other camera apps. Connect the cameras.
2. Each channel has Resolution, FPS, and Input controls. Set them before
   selecting a source. Defaults: 1280x720, 30 FPS, MJPG.
3. The source list refreshes automatically on launch. If necessary, choose
   DSHOW or MSMF and click Refresh. These lists are backend-specific.
4. Select one different source in each slot. Live preview starts immediately.
   Example: 0 | HD Pro Webcam C920 | DSHOW | a3b4c5d6
5. Click Details for the complete device path. Index/tag identify
   the enumerated device, not a permanent physical-location label. Indices
   and paths can change after reconnection. Cover one lens briefly and check
   the live view to identify each physical camera. Use Camera# to label location.
6. OBS Virtual Camera is explicitly marked [VIRTUAL?]. Choose physical sources
   for animal recording. A virtual camera can produce a valid placeholder
   image, so it does not necessarily trigger NO SIGNAL.
7. NO SIGNAL is shown for an empty source, connection/read error, or no fresh
   frames for over 3 seconds. A static scene or driver-repeated frames cannot
   always be distinguished from a healthy signal.
8. Changing a source reconnects that slot. Disconnect releases all
   camera handles. After changing a channel's capture settings, click its
   Apply button. Other channels keep their settings
   and preview. Disconnect all before changing backend or refreshing the list. Enumeration lists registered devices, which may still
   fail to open if busy or disconnected.
9. Selecting a source does NOT create output files. Check framing, focus,
   illumination, and animal identification during preview before recording.

CUSTOM FILENAMES
Each slot has Camera# and ID# text boxes. Both are optional.
Camera# blank: default slot number (1, 2, 3, or 4).
ID# blank: omit the ID portion.
Examples:
- Camera# blank, ID# blank: Camera1_slot1_part0001.mp4
- Camera# Left, ID# D241_288: CameraLeft_IDD241_288_slot1_part0001.mp4
The literal prefix is ID; enter D241_288 rather than IDD241_288 if desired.
A slot suffix prevents collisions between slots with identical entered names.
Each session has a unique date/time folder. Unsafe Windows filename characters
are replaced with underscores, trailing dots/spaces removed, and each entered
component limited to 48 characters. Original inputs are retained in metadata.
The GUI displays the sanitized first-segment filename before recording.
Names and source selectors are locked during recording. Editing capture
settings does not affect already connected sources; reconnect to apply changes.

RECORD
1. Choose output folder, Minutes, Segment minutes, and MP4 or AVI.
2. Select sources in 1 to 4 channels. Leave unused source selectors empty.
   Every selected channel must have a fresh live preview; an unavailable
   selected channel blocks start rather than being silently skipped.
3. Click Start. The encoders are prepared first, then
   a shared software start signal is released. The status changes to RECORDING.
4. Stop closes videos and returns to preview mode.
   The duration limit does this automatically. Preview can continue while
   animals are changed and labels entered for the next recording session.
5. Wait for Recording finished before disconnecting cameras or closing.

DEFAULT OUTPUT AND METADATA
MP4 with MPEG-4 Part 2 (mp4v), not H.264; AVI/MJPG remains selectable.
Default duration: 60 minutes; configurable beyond one hour. Default segment:
10 minutes. Each slot saves its own video segments and matching timestamp CSV.
Raw video has no GUI labels, NO SIGNAL text, or preview resizing added to it.
Both video codecs are lossy. Verify fine body-part details before pose analysis.
Summary JSON files contain source identity, actual capture dimensions, entered
labels, submitted frame counts, read failures, timing, and completion reason.
session.json records jobs/settings; start_timing.json records the shared start
reference; gui_log.txt records GUI events. No audio is recorded.

TIMING LIMITATIONS
Software coordination is not exposure-level hardware synchronization. USB,
sensor, and driver delays can differ. Use hardware-triggered cameras if strict
synchronization is required. A common flash can help assess alignment offsets.
CSV timestamps measure host receipt just after cap.read returns, not exposure.
Video uses the requested fixed FPS, without duplicate-frame padding. If actual
acquisition is 25 FPS while output is 30 FPS, one real hour plays in about
50 minutes. Check timestamps and actual FPS before duration/speed/frequency
analysis or fixed-FPS DLC/KPMS workflows. Normalize the time axis if required.
Read failures do not count every frame lost inside a camera/driver. CSV rows
represent frames submitted to the encoder; verify decoded video frame counts.

LONG RECORDINGS / ERRORS
Use AC power, disable sleep/hibernation and USB power saving, prefer local SSD
storage, and avoid overloading a single USB controller or hub. Fix lighting,
exposure, focus, and white balance using camera controls where supported.
Camera errors request all recordings to stop. Preview may continue for healthy
sources. If a driver blocks in capture.read, normal finalization can be delayed.
The program waits for recording files to close; do not force-end it.
Sources can be disconnected after recording; a stuck preview-only process is
terminated after 5 seconds to release it, with no active recording at that point.
Start is blocked below 5 GiB free; stop is requested below 2 GiB. Neither
threshold estimates one-hour capacity. Estimate size with a short four-camera
test and leave at least 30% extra space. Segmentation limits interruption impact
but sudden power loss/forced termination can corrupt the current video segment.

VALIDATION
Passed syntax, filename/default/sanitization checks, identical-name and virtual
warning checks, simulated persistent-preview -> recording -> preview -> second
recording transitions, segmentation/timestamp/frame-index checks, and offline
Windows wheel dependency resolution. Also tested four concurrent simulated
channels with different resolution/FPS/input-format requests, AUTO leaving
FourCC unset, driver substitution metadata, and separate output files. The simulation uses mocked capture/encoder
interfaces and does not validate real encoding. The ZIP passes CRC integrity
checks. Windows GUI rendering, physical-camera mapping, real encoding, and
long-duration hardware stability remain to be tested on your computer.
First run a short test, then at least 65 minutes with all four cameras before
formal experiments. The new enumeration wheel is included for offline setup.

BLACK-SCREEN DIAGNOSIS
Test the affected source alone, with other source selectors empty. For a
generic webcam, try 640x480,15 FPS,AUTO and apply/reconnect. For C920s,
MJPG is another available test choice. These are diagnostic settings, not
guaranteed supported modes. Then add other sources one at a time. All four
cameras may still exceed available USB bandwidth or power; parameter controls
do not remove hardware limits. The preview shows measured FPS even before
recording, which helps assess stability. Different selected FPS values do not
produce frame-for-frame synchronized recordings.
