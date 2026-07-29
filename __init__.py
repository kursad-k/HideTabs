# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2025 — Hide N-Panel Tabs Extension

"""Blender 4.2+ Extension: Hide N-Panel Tabs

Discovers all tab categories in the View3D N-Panel and lets you show/hide them
individually or in bulk via checkboxes.

Usage
-----
1. Open Blender 4.2+
2. Edit > Preferences > Extensions > Install
3. Select this folder (it will auto-detect blender_manifest.toml)
4. Enable the extension
5. Press N in the 3D Viewport → "Hide NPanel Tabs" tab appears
"""

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Panel, Operator, AddonPreferences
from bpy.app.handlers import persistent


# ──────────────────────────────────────────────────────────────
# Extension ID — must match blender_manifest.toml [manifest].id
# ──────────────────────────────────────────────────────────────
EXTENSION_ID = "Addon_HideTabs"
ADDON_KEY = __package__ or __name__
MANAGER_CATEGORY = "👁"
FALLBACK_CATEGORY = "Misc"

# Keep references to panels after they are unregistered. Blender removes
# unregistered classes from bpy.types, so rediscovery alone cannot restore them.
_panel_classes_by_category = {}
_msgbus_owner = object()
_applying_visibility = False


# ──────────────────────────────────────────────────────────────
# Helpers — discover & toggle categories
# ──────────────────────────────────────────────────────────────

def _get_addon_preferences():
    """Return this addon's preferences, or None while Blender is initializing."""
    addons = bpy.context.preferences.addons
    for key in (ADDON_KEY, EXTENSION_ID, __name__):
        addon = addons.get(key)
        if addon:
            return addon.preferences
    return None


def _get_hidden_categories() -> set:
    """Return the set of globally hidden tab category names."""
    hidden = set()
    prefs = _get_addon_preferences()
    if prefs is None:
        return hidden

    for cat in prefs.categories_list.split(","):
        cat = cat.strip()
        if cat and cat not in hidden:
            hidden.add(cat)
    return hidden


def _set_hidden_categories(hidden: set) -> None:
    """Persist the set of globally hidden categories to addon preferences."""
    prefs = _get_addon_preferences()
    if prefs is None:
        return

    prefs.categories_list = ",".join(sorted(hidden))


def _get_scene_category_overrides(context=None) -> tuple[set, set]:
    """Return the scene's explicit hidden and visible category overrides."""
    hidden = set()
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    hidden_list = getattr(scene, "hide_tabs_categories_list", "") if scene else ""
    visible_list = getattr(scene, "hide_tabs_visible_categories_list", "") if scene else ""

    for cat in hidden_list.split(","):
        cat = cat.strip()
        if cat and cat not in hidden:
            hidden.add(cat)
    visible = {cat.strip() for cat in visible_list.split(",") if cat.strip()}
    return hidden, visible


def _get_scene_hidden_categories(context=None) -> set:
    """Return categories explicitly hidden by the current scene."""
    return _get_scene_category_overrides(context)[0]


def _set_scene_category_overrides(hidden: set, visible: set, context=None) -> None:
    """Persist both sides of the scene visibility override."""
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    if hasattr(scene, "hide_tabs_categories_list"):
        scene.hide_tabs_categories_list = ",".join(sorted(hidden))
    if hasattr(scene, "hide_tabs_visible_categories_list"):
        scene.hide_tabs_visible_categories_list = ",".join(sorted(visible))


def _is_category_hidden(category: str, context=None) -> bool:
    """Resolve scene overrides first, then fall back to Preferences."""
    scene_hidden, scene_visible = _get_scene_category_overrides(context)
    if category in scene_hidden:
        return True
    if category in scene_visible:
        return False
    return category in _get_hidden_categories()


def _should_list_manager_category() -> bool:
    """Return whether this addon's own management tab should be listed."""
    prefs = _get_addon_preferences()
    return bool(prefs and prefs.show_self_category)


def _iter_panel_classes():
    """Yield currently registered Panel classes that may own UI categories."""
    seen = set()
    for cls in bpy.types.Panel.__subclasses__():
        if not getattr(cls, "is_registered", False):
            continue
        seen.add(cls)
        yield cls

    for name in dir(bpy.types):
        value = getattr(bpy.types, name, None)
        if (
            isinstance(value, type)
            and issubclass(value, Panel)
            and value not in seen
            and getattr(value, "is_registered", False)
        ):
            seen.add(value)
            yield value


def _remember_panel_class(cls) -> None:
    """Cache a registered panel so hiding it does not lose its class reference."""
    if not _is_view3d_ui_panel(cls):
        return
    category = _get_panel_category(cls)
    classes = _panel_classes_by_category.setdefault(category, [])
    if cls not in classes:
        classes.append(cls)


def _discover_panel_classes() -> None:
    for cls in _iter_panel_classes():
        _remember_panel_class(cls)


def _is_view3d_ui_panel(cls) -> bool:
    """Return whether a Panel class belongs to the View3D sidebar region."""
    return (
        getattr(cls, "bl_space_type", None) == "VIEW_3D"
        and getattr(cls, "bl_region_type", None) == "UI"
    )


def _get_panel_category(cls) -> str:
    """Return Blender's effective sidebar category for a Panel class."""
    return (getattr(cls, "bl_category", None) or FALLBACK_CATEGORY).strip()


def _get_all_categories() -> list:
    """Return a sorted list of all active N-Panel tab categories."""
    _discover_panel_classes()
    categories = []
    seen = set()
    list_manager_category = _should_list_manager_category()
    stored_categories = (
        _get_hidden_categories()
        | _get_scene_category_overrides()[0]
        | _get_scene_category_overrides()[1]
    )
    for category in list(_panel_classes_by_category) + sorted(stored_categories):
        if not category or category in seen:
            continue
        if not list_manager_category and category == MANAGER_CATEGORY:
            continue

        seen.add(category)
        categories.append(category)
    return categories


def _unregister_category(category: str) -> None:
    """Hide all panels belonging to a specific category."""
    _discover_panel_classes()
    for cls in reversed(_panel_classes_by_category.get(category, [])):
        if getattr(cls, "is_registered", False):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass


def _register_category(category: str) -> None:
    """Show all panels belonging to a specific category."""
    for cls in _panel_classes_by_category.get(category, []):
        if not getattr(cls, "is_registered", False):
            try:
                bpy.utils.register_class(cls)
            except Exception:
                pass


def _apply_hidden_categories() -> None:
    """Apply effective Preferences defaults and scene overrides."""
    global _applying_visibility
    if _applying_visibility:
        return

    _applying_visibility = True
    try:
        _discover_panel_classes()
        hidden, visible = _get_scene_category_overrides()
        categories = set(_panel_classes_by_category) | _get_hidden_categories() | hidden | visible
        for category in categories:
            if _is_category_hidden(category):
                _unregister_category(category)
            else:
                _register_category(category)
    finally:
        _applying_visibility = False


def _active_scene_changed() -> None:
    """Reapply visibility only when Blender reports an active-scene change."""
    _apply_hidden_categories()


def _subscribe_scene_changes() -> None:
    """Install the event-driven active-scene subscription."""
    bpy.msgbus.clear_by_owner(_msgbus_owner)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Window, "scene"),
        owner=_msgbus_owner,
        args=(),
        notify=_active_scene_changed,
        options={"PERSISTENT"},
    )


@persistent
def _hide_tabs_load_post(_dummy):
    _subscribe_scene_changes()
    _apply_hidden_categories()


# ──────────────────────────────────────────────────────────────
# Addon Preferences
# ──────────────────────────────────────────────────────────────

class HIDE_TABS_Preferences(AddonPreferences):
    """Store the list of hidden category names as a comma-separated string."""

    bl_idname = ADDON_KEY

    categories_list: StringProperty(
        name="Hidden Categories",
        default="",
        description="Comma-separated list of hidden tab category names",
    )
    show_self_category: BoolProperty(
        name="self",
        default=False,
        description="Include this addon's own management tab in the category list",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "show_self_category", text="self")
        layout.operator("hide_tabs.restore_manager", text="unhide")
        layout.operator("hide_tabs.refresh_categories", text="Refresh Tabs", icon="FILE_REFRESH")

        all_cats = _get_all_categories()
        hidden = _get_hidden_categories()

        if not all_cats:
            layout.label(text="No N-Panel tabs found.")
            return

        layout.label(text="Toggle visibility of each tab:")
        for cat in all_cats:
            row = layout.row(align=True)
            icon = "CHECKBOX_HLT" if cat not in hidden else "CHECKBOX_DEHLT"
            op = row.operator(
                HIDE_TABS_OT_toggle_category.bl_idname,
                text=cat,
                icon=icon,
            )
            op.category = cat
            op.storage = "ADDON"

        layout.separator()
        col = layout.column(align=True)
        col.operator("hide_tabs.hide_selected", text="Hide Selected").storage = "ADDON"
        col.operator("hide_tabs.unhide_all", text="Unhide All").storage = "ADDON"


# ──────────────────────────────────────────────────────────────
# Operators
# ──────────────────────────────────────────────────────────────

class HIDE_TABS_OT_hide_selected(Operator):
    """Hide selected tab categories"""

    bl_idname = "hide_tabs.hide_selected"
    bl_label = "Hide Selected"
    bl_description = "Hide all selected tab categories"
    bl_options = {"REGISTER", "UNDO"}

    storage: StringProperty(default="SCENE")

    def execute(self, context):
        use_addon_preferences = self.storage == "ADDON"
        hidden = (
            _get_hidden_categories()
            if use_addon_preferences
            else _get_scene_hidden_categories(context)
        )
        all_cats = _get_all_categories()
        for cat in all_cats:
            if cat not in hidden:
                _unregister_category(cat)
        if use_addon_preferences:
            _set_hidden_categories(set(all_cats))
        else:
            _set_scene_category_overrides(set(all_cats), set(), context)
        self.report({"INFO"}, f"Hidden: {', '.join(set(all_cats) - hidden) or 'none'}.")
        return {"FINISHED"}


class HIDE_TABS_OT_unhide_all(Operator):
    """Unhide all tab categories"""

    bl_idname = "hide_tabs.unhide_all"
    bl_label = "Unhide All"
    bl_description = "Show all hidden tab categories"
    bl_options = {"REGISTER", "UNDO"}

    storage: StringProperty(default="SCENE")

    def execute(self, context):
        use_addon_preferences = self.storage == "ADDON"
        all_cats = _get_all_categories()

        # Preferences reset is the recovery path even when every tab,
        # including this add-on's own manager, has been hidden.
        if use_addon_preferences:
            _set_hidden_categories(set())
            for scene in bpy.data.scenes:
                if hasattr(scene, "hide_tabs_categories_list"):
                    scene.hide_tabs_categories_list = ""
                if hasattr(scene, "hide_tabs_visible_categories_list"):
                    scene.hide_tabs_visible_categories_list = ""
            for cat in list(_panel_classes_by_category):
                _register_category(cat)
            self.report({"INFO"}, "Visibility reset to defaults; all tabs restored.")
            return {"FINISHED"}

        _set_scene_category_overrides(set(), set(), context)
        _apply_hidden_categories()
        self.report({"INFO"}, "Scene overrides cleared; Preferences defaults restored.")
        return {"FINISHED"}


class HIDE_TABS_OT_toggle_category(Operator):
    """Toggle visibility of a single tab category"""

    bl_idname = "hide_tabs.toggle_category"
    bl_label = "Toggle Category"
    bl_description = "Toggle visibility of a single tab"
    bl_options = {"REGISTER", "UNDO"}

    category: StringProperty()
    storage: StringProperty(default="SCENE")

    def execute(self, context):
        use_addon_preferences = self.storage == "ADDON"
        if use_addon_preferences:
            hidden = _get_hidden_categories()
            if self.category in hidden:
                hidden.discard(self.category)
            else:
                hidden.add(self.category)
            _set_hidden_categories(hidden)
        else:
            hidden, visible = _get_scene_category_overrides(context)
            new_hidden = not _is_category_hidden(self.category, context)
            hidden.discard(self.category)
            visible.discard(self.category)
            preference_hidden = self.category in _get_hidden_categories()
            if new_hidden != preference_hidden:
                (hidden if new_hidden else visible).add(self.category)
            _set_scene_category_overrides(hidden, visible, context)

        if _is_category_hidden(self.category, context):
            _unregister_category(self.category)
        else:
            _register_category(self.category)
        return {"FINISHED"}


class HIDE_TABS_OT_restore_manager(Operator):
    """Restore this addon's N-panel tab"""

    bl_idname = "hide_tabs.restore_manager"
    bl_label = "unhide"
    bl_description = "Show this addon's N-panel tab again"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        addon_hidden = _get_hidden_categories()
        addon_hidden.discard(MANAGER_CATEGORY)
        _set_hidden_categories(addon_hidden)
        scene_hidden, scene_visible = _get_scene_category_overrides(context)
        scene_hidden.discard(MANAGER_CATEGORY)
        scene_visible.add(MANAGER_CATEGORY)
        _set_scene_category_overrides(scene_hidden, scene_visible, context)
        _register_category(MANAGER_CATEGORY)
        return {"FINISHED"}


class HIDE_TABS_OT_refresh_categories(Operator):
    """Refresh the list of currently registered N-panel categories"""

    bl_idname = "hide_tabs.refresh_categories"
    bl_label = "Refresh Tabs"
    bl_description = "Refresh the list of tabs from currently registered panels"

    def execute(self, context):
        screen = getattr(context, "screen", None)
        if screen:
            for area in screen.areas:
                if area.type in {"VIEW_3D", "PREFERENCES"}:
                    area.tag_redraw()

        category_count = len(_get_all_categories())
        self.report({"INFO"}, f"Found {category_count} active N-panel tabs.")
        return {"FINISHED"}


# ──────────────────────────────────────────────────────────────
# N-Panel UI
# ──────────────────────────────────────────────────────────────

class VIEW3D_PT_hide_tabs(Panel):
    """N-Panel tab for managing tab visibility"""

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = MANAGER_CATEGORY
    bl_label = "Hide NPanel Tabs"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.operator(
            HIDE_TABS_OT_refresh_categories.bl_idname,
            text="Refresh Tabs",
            icon="FILE_REFRESH",
        )
        all_cats = _get_all_categories()

        if not all_cats:
            layout.label(text="No N-Panel tabs found.")
            return

        for cat in all_cats:
            row = layout.row(align=True)
            icon = "CHECKBOX_DEHLT" if _is_category_hidden(cat, context) else "CHECKBOX_HLT"
            op = row.operator(
                HIDE_TABS_OT_toggle_category.bl_idname,
                text=cat,
                icon=icon,
            )
            op.category = cat
            op.storage = "SCENE"

        layout.separator()
        col = layout.column(align=True)
        col.operator("hide_tabs.hide_selected", text="Hide Selected")
        col.operator("hide_tabs.unhide_all", text="Unhide All")


# ──────────────────────────────────────────────────────────────
# Registration
# ──────────────────────────────────────────────────────────────

classes = (
    HIDE_TABS_Preferences,
    HIDE_TABS_OT_hide_selected,
    HIDE_TABS_OT_unhide_all,
    HIDE_TABS_OT_toggle_category,
    HIDE_TABS_OT_restore_manager,
    HIDE_TABS_OT_refresh_categories,
    VIEW3D_PT_hide_tabs,
)


def register():
    from bpy.utils import register_class

    for cls in classes:
        register_class(cls)
    bpy.types.Scene.hide_tabs_categories_list = StringProperty(
        name="Hidden N-Panel Categories",
        default="",
        description="Scene-specific comma-separated list of hidden N-panel tab categories",
    )
    bpy.types.Scene.hide_tabs_visible_categories_list = StringProperty(
        name="Visible N-Panel Category Overrides",
        default="",
        description="Scene-specific categories shown despite Preferences defaults",
    )
    if _hide_tabs_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_hide_tabs_load_post)
    _subscribe_scene_changes()
    _apply_hidden_categories()


def unregister():
    from bpy.utils import unregister_class

    bpy.msgbus.clear_by_owner(_msgbus_owner)
    if _hide_tabs_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_hide_tabs_load_post)
    if hasattr(bpy.types.Scene, "hide_tabs_categories_list"):
        del bpy.types.Scene.hide_tabs_categories_list
    if hasattr(bpy.types.Scene, "hide_tabs_visible_categories_list"):
        del bpy.types.Scene.hide_tabs_visible_categories_list

    for category in list(_panel_classes_by_category):
        _register_category(category)

    for cls in reversed(classes):
        unregister_class(cls)


if __name__ == "__main__":
    register()
