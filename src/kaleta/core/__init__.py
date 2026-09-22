# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pure, dependency-free helpers shared by every layer above.

Nothing here touches the database, the HTTP layer or NiceGUI — a module in
``kaleta.core`` may be imported from a model, a service or a view without
dragging anything else along.
"""
