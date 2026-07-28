# Hide N-Panel Tabs

A Blender extension that removes sidebar clutter. Install enough add-ons and the N-Panel in the
3D Viewport turns into a wall of tabs you have to scroll through. The usual fix is to disable the
add-ons you are not using, which also takes away their functionality. This extension takes a
different route: it unregisters the panels behind a tab so the tab disappears, while the add-on
itself stays enabled and everything else it provides keeps working.

Visibility is stored in two places. The N-Panel list writes to the current scene, so it travels
inside the .blend file and each project keeps its own sidebar layout. The list in Preferences
writes to the add-on preferences and applies to every file you open.

## Features

- Toggle any View3D sidebar tab on or off without disabling the add-on that owns it
- Tab categories are discovered from the panels registered at that moment, third-party add-ons
  included, and listed in the order Blender registered them
- Per-scene visibility saved in the .blend file, reapplied automatically on file load
- Global visibility in Preferences for tabs you never want to see in any file
- Hide Selected and Unhide All for clearing or restoring a whole list at once
- Refresh Tabs to rescan after enabling or disabling other add-ons
- The management tab itself can be hidden; a toggle plus an unhide button in Preferences brings
  it back


## Requirements

Blender 4.2.0 or newer. The extension uses the 4.2 extensions platform, so it will not install
on older releases.

## Installation

### From a release archive

1. Download the `.zip` from the [Releases](https://github.com/kursad-k/HideTabs/releases) page.
   Do not unpack it.
2. In Blender, open `Edit > Preferences > Add-ons`.
3. Click the arrow button in the top right corner and choose `Install from Disk`.
4. Pick the downloaded `.zip` and confirm.
5. Make sure the checkbox next to `Hide N-Panel Tabs` is ticked.

### From source

1. Clone or download this repository.
2. Copy the folder into your Blender extensions directory, keeping `blender_manifest.toml` and
   `__init__.py` together at its top level:
   - Windows: `%APPDATA%\Blender Foundation\Blender\4.2\extensions\user_default\`
   - macOS: `~/Library/Application Support/Blender/4.2/extensions/user_default/`
   - Linux: `~/.config/blender/4.2/extensions/user_default/`
3. Restart Blender, then enable `Hide N-Panel Tabs` under `Edit > Preferences > Add-ons`.

Substitute your Blender version for `4.2` in those paths.

## Usage

Press `N` in the 3D Viewport and switch to the eye-icon tab. Every active sidebar category is
listed with a checkbox: a ticked box means the tab is visible, an empty box means it is hidden.
Click a name to flip it. Changes here belong to the current scene, so save the file to keep them.

`Hide Selected` hides every category in the list. `Unhide All` brings them all back. Use
`Refresh Tabs` after you enable or disable another add-on so the list matches what is actually
registered.

For settings that should apply to every file, open `Edit > Preferences > Add-ons`, expand
`Hide N-Panel Tabs`, and use the list there instead. It has the same controls and writes to the
add-on preferences rather than the scene. A tab hidden in either place stays hidden, and unhiding
it in one place will not override the other.

To take this add-on's own tab out of the sidebar, tick `self` in Preferences so it appears in the
category lists, then hide it like any other. The `unhide` button in Preferences restores it.

## How it works

Hiding a tab calls `bpy.utils.unregister_class` on every `VIEW_3D` / `UI` panel whose
`bl_category` matches that name, and unhiding registers them again. Nothing is patched or
monkey-wrapped, and no other add-on's code is modified. Two consequences worth knowing:

- Hidden panels are genuinely unregistered, so scripts that reference those panel classes
  directly will not find them until you unhide the tab.
- The list only shows tabs whose panels exist right now. An add-on that registers panels lazily
  will not appear until it has done so; hit `Refresh Tabs` afterwards.

Panels without a `bl_category` are grouped under `Misc`, matching Blender's own behaviour.

## License

GPL-3.0-or-later.