from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera


class VolumeViewerInteractorStyle(vtkInteractorStyleTrackballCamera):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self._last_pos = None
        self._mode = None  # rotate の状態変数
        self._interactive_active = False

        self.RemoveObservers("LeftButtonPressEvent")
        self.AddObserver("LeftButtonPressEvent", self.on_left_button_down)
        self.RemoveObservers("LeftButtonReleaseEvent")
        self.AddObserver("LeftButtonReleaseEvent", self.on_left_button_up)
        self.AddObserver("MouseMoveEvent", self.on_mouse_move)

        self.RemoveObservers("RightButtonPressEvent")
        self.AddObserver("RightButtonPressEvent", self.on_right_button_down)
        self.RemoveObservers("RightButtonReleaseEvent")
        self.AddObserver("RightButtonReleaseEvent", self.on_right_button_up)

    def _set_interaction_active(self, active: bool) -> None:
        if self._interactive_active == active:
            return
        self._interactive_active = active
        if self.parent is not None and hasattr(self.parent, "apply_interactive_quality"):
            self.parent.apply_interactive_quality(active)

    def on_left_button_down(self, obj, event):
        iren = self.GetInteractor()
        self._set_interaction_active(True)

        if iren.GetShiftKey():
            self.StartSpin()
            self._mode = 'spin'
        else:
            self._mode = 'rotate'
            self._last_pos = iren.GetEventPosition()
        return

    def on_right_button_down(self, obj, event):
        iren = self.GetInteractor()
        self._set_interaction_active(True)
        self._last_pos = iren.GetEventPosition()
        self._mode = 'ww/wl'

    def on_mouse_move(self, obj, event):
        if self._mode == 'spin':
            self.Spin()
        elif self._mode == 'rotate':
            iren = self.GetInteractor()
            x, y = iren.GetEventPosition()
            lx, ly = self._last_pos
            dx, dy = x - lx, y - ly
            self.parent.rotate_camera(dx, dy)
            self._last_pos = (x, y)
        elif self._mode == 'ww/wl':
            iren = self.GetInteractor()
            x, y = iren.GetEventPosition()
            lx, ly = self._last_pos
            dx, dy = x - lx, y - ly
            self.parent.adjust_window_settings(dx, dy)
            self._last_pos = (x, y)
        # return

    def on_left_button_up(self, obj, event):
        if self._mode == 'spin':
            self.EndSpin()
        self._mode = False
        self._set_interaction_active(False)
        return

    def on_right_button_up(self, obj, event):
        self._mode = False
        self._set_interaction_active(False)
        return