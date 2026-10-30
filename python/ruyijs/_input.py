"""Trusted input is created by the existing native Interaction owner."""


def _frame_path(frame):
    """Validate a frame path: child indices separated by slashes ("0", "0/1")."""
    if frame is None:
        return ""
    if not isinstance(frame, str):
        raise TypeError("frame must be a string")
    if frame == "":
        return frame
    for part in frame.split("/"):
        if not part.isdigit():
            raise ValueError("frame path must be child indices separated by slashes")
    return frame


class InputControl:
    def dispatch_input(self, event_type, *, target="document", frame=None,
                       selector=None, **init):
        """Dispatch one trusted Mouse/Pointer event and return True on delivery.

        target is a JavaScript expression evaluated in this Context. The event
        is created in that target's realm. Coordinate/flag fields use the native
        event dictionary; timeStamp reads the Context's scheduling clock. No
        layout, hit testing, or automatic compatibility mouse event is generated.

        frame addresses a child frame of the active document ("0", "0/1"); the
        target expression is then evaluated in that frame's realm.

        selector names the element with a CSS selector instead of an
        expression. The lookup descends into shadow roots, so it reaches an
        element the page's own script cannot see.
        """
        if not isinstance(event_type, str) or not isinstance(target, str):
            raise TypeError("input type and target must be strings")
        if selector is not None and not isinstance(selector, str):
            raise TypeError("selector must be a string")
        path = _frame_path(frame)
        self._callbacks.guard()
        with self._lock:
            fields = {"type": event_type, "target": target, "init": init, "frame": path}
            if selector is not None:
                fields["selector"] = selector
            return self._request("input", **fields)

    def click(self, target=None, *, hold_ms=80, frame=None, selector=None):
        """Click the element `target` (a JavaScript expression) as a user does.

        Trusted pointer/mouse events in Firefox's order at the element's center:
        enter/over, move, down (which moves focus), `hold_ms` of running event
        loop, up, then click (a PointerEvent) and its activation - a submit
        button submits its form, a link navigates.

        frame addresses a child frame of the active document ("0", "0/1"); the
        expression is then evaluated in that frame's realm and the click
        happens inside that frame.

        selector instead names the element with a CSS selector. The lookup
        descends into shadow roots, open and closed, so it reaches an element
        the page's own script cannot see.
        """
        if target is not None and not isinstance(target, str):
            raise TypeError("click target must be a string expression")
        if selector is not None and not isinstance(selector, str):
            raise TypeError("click selector must be a string")
        if target is None and selector is None:
            raise TypeError("click needs a target or a selector")
        fields = {"action": "click", "hold_ms": hold_ms, "frame": _frame_path(frame)}
        if target is not None:
            fields["target"] = target
        if selector is not None:
            fields["selector"] = selector
        return self._user(**fields)

    def type(self, text, *, target=None, interval_ms=60, frame=None):
        """Type `text` into the focused element (or focus `target` first).

        Each character is keydown, keypress, beforeinput, the insertion, input
        and keyup, with `interval_ms` of running event loop between characters.

        frame addresses a child frame of the active document ("0", "0/1").
        """
        if not isinstance(text, str) or (target is not None and not isinstance(target, str)):
            raise TypeError("type text and target must be strings")
        fields = {"text": text, "interval_ms": interval_ms, "frame": _frame_path(frame)}
        if target is not None:
            fields["target"] = target
        return self._user(action="type", **fields)

    def press(self, key, *, target=None, frame=None):
        """Press one named key: Enter, Backspace, Tab, Escape or an arrow key.

        Enter inserts a line break in a textarea and submits from an input.

        frame addresses a child frame of the active document ("0", "0/1").
        """
        if not isinstance(key, str) or (target is not None and not isinstance(target, str)):
            raise TypeError("press key and target must be strings")
        fields = {"key": key, "frame": _frame_path(frame)}
        if target is not None:
            fields["target"] = target
        return self._user(action="press", **fields)

    def _user(self, **fields):
        self._callbacks.guard()
        with self._lock:
            return self._request("user", **fields)
