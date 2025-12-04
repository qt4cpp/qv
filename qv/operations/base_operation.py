"""
Base class for operations.

Generic operations interface that doesn't on specific viewer types.
Assumes image data is represented as vtk.vtkImageData.
"""

import logging
from abc import ABC, abstractmethod

import vtk


logger = logging.getLogger(__name__)


class BaseOperation(ABC):
    """
    Base class for all operations.

    This class provides a common interface for operations that can be
    performed on image data.

    Notes:
        - It does not depend on any specific *viewer* type.
        - It assumes image data is represented as vtk.vtkImageData.
        - Subclasses are responsible for:
            * calling `_backup_image_data(...)` before modifying the image.
            * managing `is_active` in their lifecycle (start/reset/etc).
    """

    def __init__(self):
        """Initialize the operation."""
        self.backup_image: vtk.vtkImageData | None = None
        self.is_active: bool = False
        self._operation_name: str = self.__class__.__name__

    # =====================================================
    # Lifecycle interface
    # =====================================================

    @abstractmethod
    def start(self) -> None:
        """
        Start the operation.

        This method should set up any necessary state and UI elements
        for the operation to begin.
        Typically, sublcasses should set `self.is_active = True` here.
        """
        raise NotImplementedError

    @abstractmethod
    def apply(self) -> None:
        """
        Apply the operation to the image data.

        This method should perform the actual operation on the image data.
        """
        raise NotImplementedError

    @abstractmethod
    def cancel(self) -> None:
        """
        Cancel the operation.

        This method should revert any changes made by the operation and clean up
        any temporary data and UI elements.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """
        Reset the operation to its initial state.

        This method should revert any changes made by the operation
        and restore the image data to its original state.
        Typically, sublcasses should set `self.is_active = False` here.
        """
        raise NotImplementedError

    # =====================================================
    # Common helpers
    # =====================================================

    def is_operation_active(self) -> bool:
        """
        Check if the operation is currently active.

        :return: True if the operation is active, False otherwise.
        """
        return self.is_active


    def _backup_image_data(self, image: vtk.vtkImageData) -> bool:
        """
        Create a backup of the given image data.

        :return:
        """
        if image is None:
            logger.warning("[%s] Cannot backup None image data.", self._operation_name)
            return False

        self.backup_image = vtk.vtkImageData()
        self.backup_image.DeepCopy(image)
        logger.debug("[%s] Backup created.", self._operation_name)
        return True

    def _has_backup(self) -> bool:
        """
        Check if the operation has backup image data.

        :return: True if backup exists, False otherwise.
        """
        return self.backup_image is not None
