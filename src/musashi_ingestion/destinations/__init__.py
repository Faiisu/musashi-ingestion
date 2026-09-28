"""Delivery adapters. Each ``send`` returns only after remote acceptance."""

from .worker import DeliveryWorker
from .factory import DestinationSetupError, create_destination

__all__ = ["DeliveryWorker", "DestinationSetupError", "create_destination"]
