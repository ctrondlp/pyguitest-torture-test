"""The tab pages that make up TortureTest, in display order."""

from __future__ import annotations

from .buttons import ButtonsPage
from .choosers import ChoosersPage
from .containers import ContainersPage
from .displays import DisplaysPage
from .imagesearch import ImageSearchPage
from .inputs import InputsPage
from .itemviews import ItemViewsPage
from .kitchensink import KitchenSinkPage
from .ranges import RangesPage

# Each entry is a `Page` subclass; the main window instantiates one per tab.
PAGES: tuple[type, ...] = (
    ButtonsPage,
    InputsPage,
    ChoosersPage,
    ItemViewsPage,
    DisplaysPage,
    ImageSearchPage,
    RangesPage,
    ContainersPage,
    KitchenSinkPage,
)

__all__ = ["PAGES"]
