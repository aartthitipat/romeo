"""Read the Windows UI Automation tree with pywinauto (cheaper than vision)."""

from __future__ import annotations

from typing import Any, Optional


def _desktop():
    from pywinauto import Desktop

    return Desktop(backend="uia")


def list_windows() -> list[dict[str, Any]]:
    out = []
    for w in _desktop().windows():
        try:
            if not w.is_visible() or not w.window_text():
                continue
            r = w.rectangle()
            out.append(
                {
                    "title": w.window_text(),
                    "handle": w.handle,
                    "process_id": w.process_id(),
                    "rect": [r.left, r.top, r.right, r.bottom],
                }
            )
        except Exception:  # windows can disappear while iterating
            continue
    return out


def _window(title: Optional[str]):
    desk = _desktop()
    if title:
        return desk.window(title_re=f".*{title}.*", visible_only=True)
    from pywinauto import findwindows

    handle = findwindows.find_element(active_only=True, backend="uia").handle
    return desk.window(handle=handle)


def ui_tree(title: Optional[str] = None, max_depth: int = 4, max_nodes: int = 300):
    """Compact tree of controls: name, type, center point, enabled."""
    root = _window(title).wrapper_object()
    nodes: list[str] = []

    def walk(el, depth: int) -> None:
        if depth > max_depth or len(nodes) >= max_nodes:
            return
        try:
            info = el.element_info
            r = el.rectangle()
            cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
            name = (info.name or "").strip()
            if name or info.control_type in ("Button", "Edit", "MenuItem", "ListItem"):
                nodes.append(
                    f"{'  ' * depth}- [{info.control_type}] {name!r} @({cx},{cy})"
                    + ("" if el.is_enabled() else " (disabled)")
                )
            for child in el.children():
                walk(child, depth + 1)
        except Exception:
            return

    walk(root, 0)
    return root.window_text(), "\n".join(nodes)


def find_element(
    name: str, control_type: Optional[str] = None, title: Optional[str] = None
) -> dict[str, Any]:
    criteria: dict[str, Any] = {"title_re": f".*{name}.*"}
    if control_type:
        criteria["control_type"] = control_type
    el = _window(title).child_window(**criteria).wrapper_object()
    r = el.rectangle()
    return {
        "name": el.element_info.name,
        "control_type": el.element_info.control_type,
        "center": [(r.left + r.right) // 2, (r.top + r.bottom) // 2],
        "rect": [r.left, r.top, r.right, r.bottom],
    }


def focused_window_title() -> str:
    try:
        return _window(None).window_text()
    except Exception:
        return ""
