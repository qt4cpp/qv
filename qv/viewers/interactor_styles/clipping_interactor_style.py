"""
Interactor style for Clipping operations
"""

import logging

import vtk

logger = logging.getLogger(__name__)


class ClippingInteractorStyle(vtk.vtkInteractorStyleTrackballCamera):
    """"
    Interactor style for clipping mode.

    Handles mouse events during clipping operation and delegates
    them to the clipping object.
    """

    def __init__(self, renderer: vtk.vtkRenderer, clipping_operation):
        """
        Initialize the clipping interactor style.

        :param renderer: The VTK renderer.
        :param clipping_operation: The ClippingOperation instance to handle events.
        """
        super().__init__()
        self.renderer = renderer
        self.clipping_operation = clipping_operation

        self.SetCurrentRenderer(renderer)
        self.picker = vtk.vtkCellPicker()
        self.picker.SetTolerance(0.005)

        self.AddObserver("LeftButtonPressEvent", self.OnLeftButtonDown)
        self.AddObserver("LeftButtonDoubleClickEvent", self.OnLeftButtonDoubleClick)

        logger.debug("[ClippingInteractorStyle] Initialized.")

    def OnLeftButtonDown(self, caller, event):
        """
        Handle left mouse button press.

        Converts screen coodinates to world coorinates and adds
        the point to the clipping operation.
        """
        x, y = self.GetInteractor().GetEventPosition()
        self.picker.Pick(x, y, 0, self.renderer)
        world_pt = self.picker.GetPickPosition()

        logger.debug("[ClippingInteractorStyle] Point added at screen (%d, %d) -> world %s",
                     x, y, world_pt)
        self.clipping_operation.add_selection_point(
            display_xy=(float(x), float(y)),
            world_pt=world_pt
        )

    def OnLeftButtonDoubleClick(self, caller, event):
        """
        Handle double-click event.

        Completes the region selection.
        """
        logger.debug("[ClippingInteractorStyle] Double-click detected -> completing selection.")
        self.clipping_operation.complete_selection()
