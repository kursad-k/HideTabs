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


def _get_scene_hidden_categories(context=None) -> set:
    """Return the set of hidden tab category names saved on the current scene."""
    hidden = set()
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    categories_list = getattr(scene, "hide_tabs_categories_list", "") if scene else ""

    for cat in categories_list.split(","):
        cat = cat.strip()
        if cat and cat not in hidden:
            hidden.add(cat)
    return hidden


def _set_scene_hidden_categories(hidden: set, context=None) -> None:
    """Persist the set of hidden categories on the current scene."""
    context = context or bpy.context
    scene = getattr(context, "scene", None)
    if scene is None or not hasattr(scene, "hide_tabs_categories_list"):
        return

    scene.hide_tabs_categories_list = ",".join(sorted(hidden))


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
    categories = []
    seen = set()
    list_manager_category = _should_list_manager_category()
    for cls in _iter_panel_classes():
        if not _is_view3d_ui_panel(cls):
            continue

        category = _get_panel_category(cls)
        if not category or category in seen:
            continue
        if not list_manager_category and category == MANAGER_CATEGORY:
            continue

        seen.add(category)
        categories.append(category)
    return categories


def _unregister_category(category: str) -> None:
    """Hide all panels belonging to a specific category."""
    for cls in _iter_panel_classes():
        if (
            _is_view3d_ui_panel(cls)
            and _get_panel_category(cls) == category
        ):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass


def _register_category(category: str) -> None:
    """Show all panels belonging to a specific category."""
    for cls in _iter_panel_classes():
        if (
            _is_view3d_ui_panel(cls)
            and _get_panel_category(cls) == category
        ):
            try:
                bpy.utils.register_class(cls)
            except Exception:
                pass


def _apply_hidden_categories() -> None:
    """Hide categories persisted in addon preferences or the current scene."""
    for category in _get_hidden_categories() | _get_scene_hidden_categories():
        _unregister_category(category)


@persistent
def _hide_tabs_load_post(_dummy):
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
            _set_scene_hidden_categories(set(all_cats), context)
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
        other_hidden = (
            _get_scene_hidden_categories(context)
            if use_addon_preferences
            else _get_hidden_categories()
        )
        all_cats = _get_all_categories()
        for cat in all_cats:
            if cat not in other_hidden:
                _register_category(cat)
        if use_addon_preferences:
            _set_hidden_categories(set())
        else:
            _set_scene_hidden_categories(set(), context)
        self.report({"INFO"}, "All tabs restored.")
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
        hidden = (
            _get_hidden_categories()
            if use_addon_preferences
            else _get_scene_hidden_categories(context)
        )

        if self.category in hidden:
            hidden.discard(self.category)
            other_hidden = (
                _get_scene_hidden_categories(context)
                if use_addon_preferences
                else _get_hidden_categories()
            )
            if self.category not in other_hidden:
                _register_category(self.category)
        else:
            _unregister_category(self.category)
            hidden.add(self.category)

        if use_addon_preferences:
            _set_hidden_categories(hidden)
        else:
            _set_scene_hidden_categories(hidden, context)
        return {"FINISHED"}


class HIDE_TABS_OT_restore_manager(Operator):
    """Restore this addon's N-panel tab"""

    bl_idname = "hide_tabs.restore_manager"
    bl_label = "unhide"
    bl_description = "Show this addon's N-panel tab again"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        addon_hidden = _get_hidden_categories()
        scene_hidden = _get_scene_hidden_categories(context)
        addon_hidden.discard(MANAGER_CATEGORY)
        scene_hidden.discard(MANAGER_CATEGORY)
        _set_hidden_categories(addon_hidden)
        _set_scene_hidden_categories(scene_hidden, context)
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
        hidden = _get_scene_hidden_categories(context)

        if not all_cats:
            layout.label(text="No N-Panel tabs found.")
            return

        for cat in all_cats:
            row = layout.row(align=True)
            icon = "CHECKBOX_HLT" if cat not in hidden else "CHECKBOX_DEHLT"
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
    if _hide_tabs_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_hide_tabs_load_post)
    _apply_hidden_categories()


def unregister():
    from bpy.utils import unregister_class

    if _hide_tabs_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_hide_tabs_load_post)
    if hasattr(bpy.types.Scene, "hide_tabs_categories_list"):
        del bpy.types.Scene.hide_tabs_categories_list

    for cls in reversed(classes):
        unregister_class(cls)


if __name__ == "__main__":
    register()
