"""
TODO:
  * Add support for static objects (screws), possibly for collision as well
  * Check for gantry collisions in path
  * Add Z-scanning in case of failure
  * Generate G1-Code from path
  * Add custom G-Code command for finding a path
"""
from heapq import heappop, heappush
from itertools import chain
from math import sqrt
from typing import Optional, TypeVar, Generic, Any, cast

from .geometry import Rectangle
from .printerboxes import PrinterBoxes

PointType = tuple[float, float]

class PathFinderManager:

    def __init__(self, printer: PrinterBoxes) -> None:
        self.printer = printer

    def find_path(
        self, start: PointType, goal: PointType
    ) -> Optional[list[PointType]]:
        #TODO Z-scanning etc.
        return self.find_path_at_height(start, goal, 0)

    def find_path_at_height(
        self, start: PointType, goal: PointType, height: float
    ) -> Optional[list[PointType]]:
        # Discard everything that is lower than height, and keep rectangles
        objects = iter(o.projection() for o in self.printer.objects
                       if o.max_z > height)
        # Add space for printhead to move around and padding
        spaces = [self.occupied_space(o) for o in objects]
        all_corners = chain.from_iterable(iter(o.get_corners() for o in spaces))
        vertices = [c for c in all_corners if self.filter_corner(c, spaces)]

        pf = PathFinder(vertices, spaces, start, goal)
        return pf.shortest_path()

    def occupied_space(self, obj: Rectangle) -> Rectangle:
        """Return the space for an object that we can't move into, including
        the size of the printhead as well as padding.
        """
        ph = self.printer.printhead
        pad = self.printer.padding
        return Rectangle(obj.x - ph.max_x - pad,
                         obj.y - ph.max_y - pad,
                         obj.max_x - ph.x + pad,
                         obj.max_y - ph.y + pad)

    def filter_corner(self, p: PointType, objects: list[Rectangle]) -> bool:
        # Reject points that lie outside the printbed
        if not self.printer.printbed.contains(p):
            return False
        # Reject points that lie strictly within a different object.
        # This isn't technically necessary as those points couldn't connect to
        # any others in the graph, but filtering that here should be faster as
        # it reduces the amount of vertices.
        for o in objects:
            if o.contains(p, include_edges=False):
                return False
        return True


class PathFinder:
    """
    Find a path between two points by avoiding a given set of objects in the
    form of rectangles in a plane. This is done by constructing a graph from
    all corners of the rectangles as well as the two points between which we
    want a path. Two such vertices are connected by an edge in the graph if the
    straight line between them collides with no objects. The final path is
    found by applying the A*-algorithm on that graph.
    """

    def __init__(self, vertices: list[PointType], objects: list[Rectangle],
                 start: PointType, goal: PointType):
        self.objects = objects

        # Vertices are generally referenced by their integer index.
        # This list serves mostly as a symbol table.
        self.vertices = vertices + [start, goal]
        self.n: int = len(self.vertices)

        # Indices of start/goal vertex, if set
        self.start: int = self.n - 2
        self.goal: int = self.n - 1

        # Adjacency lists, one for each node. Each adjacent node is represented
        # together with the weight of that edge. The edge relation is lazily
        # evaluated through self.adjacent(). This list serves as a cache for
        # that function.
        self.adj: list[Optional[list[tuple[int, float]]]] = [None] * self.n

    def adjacent(self, v: int) -> list[tuple[int, float]]:
        """Return all vertices adjacent to v.
        This is lazily computed because the entire edge relation is usually not
        required.
        """
        cached = self.adj[v]
        if cached is not None:
            return cached

        adjacent = [(w, self.weight(v, w))
                    for w in range(self.n)
                    if self.edge(v, w)]
        self.adj[v] = adjacent
        return adjacent

    def edge(self, v: int, w: int) -> bool:
        if v == w:
            return False

        p1 = self.vertices[v]
        p2 = self.vertices[w]
        line_box = Rectangle(*p1, *p2)

        try:
            # Inclination of the line between p1 and p2
            m = (p2[1] - p1[1]) / (p2[0] - p1[0])
            # Function for line(x) = y on that line
            line = lambda x: m * (x - p1[0]) + p1[1]
        except ZeroDivisionError:
            # p1 and p2 lie on a vertical line (have the same x value)
            m = float('inf')

        for o in self.objects:
            if m == float('inf'):
                y = max(line_box.y, o.y)
                max_y = min(line_box.max_y, o.max_y)
                if o.x < line_box.x < o.max_x and max_y > y:
                    return False
                continue

            intersection = line_box.intersection(o)
            if not intersection:
                continue

            # Critical values: y values of the line at the x-values of the
            # intersection boundaries. These must lie either both above or
            # both below the object for the line to fit.
            c1 = line(intersection.x)
            c2 = line(intersection.max_x)
            if not ((c1 <= o.y and c2 <= o.y) or
                    (c1 >= o.max_y and c2 >= o.max_y)):
                return False

        return True

    def weight(self, v: int, w: int) -> float:
        """Calculate the weight of an edge as the euclidean distance between
        its end points.
        """
        p1 = self.vertices[v]
        p2 = self.vertices[w]
        return sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

    def astar(self) -> tuple[float, list[Optional[int]]]:
        if self.start is None or self.goal is None:
            raise ValueError("Start and endpoint not set (use set_route())")
        dist: list[float] = [float('inf')] * self.n
        dist[self.start] = 0
        parent: list[Optional[int]] = [None] * self.n
        pq = EditablePQ[int]()

        pq.push(self.start, self.weight(self.start, self.goal))
        while pq.queue:
            v = pq.pop()
            if v == self.goal:
                return dist[v], parent
            for w, weight in self.adjacent(v):
                if dist[w] > dist[v] + weight:
                    parent[w] = v
                    dist[w] = dist[v] + weight
                    # pq.push either adds w or updates its priority if w is
                    # already in the queue
                    pq.push(w, dist[w] + self.weight(w, self.goal))
        return float('inf'), parent

    def shortest_path(self) -> Optional[list[PointType]]:
        """Resolve the parent relation into a path and convert indices back to
        actual points.
        """
        dist, parents = self.astar()
        if dist == float('inf'):
            return None
        # self.goal can't be None here, as that would have raised in astar()
        cur = cast(int, self.goal)
        path = [self.vertices[cur]]
        while cur != self.start:
            new = parents[cur]
            assert new is not None
            path.append(self.vertices[new])
            cur = new
        path.reverse()
        return path


T = TypeVar('T')

class EditablePQ(Generic[T]):
    """A priority queue using a heap datastructure with added functionality for
    removing/updating elements.

    The mechanism for removing and updating elements is taken from the
    documentation of the heapq module.
    """
    _REMOVED = object()

    def __init__(self) -> None:
        self.queue: list[Any] = []
        self.entry_finder: dict[T, list[Any]] = {}

    def pop(self) -> T:
        """Return the item with the lowest associated priority score, filtering
        out any entries that have been marked as removed.
        """
        while self.queue:
            prio, item = heappop(self.queue)
            if item is not self._REMOVED:
                del self.entry_finder[item]
                return item
        raise IndexError("pop from empty priority queue")

    def push(self, item: T, priority: float) -> None:
        """Add new item or update the priority of an existing one"""
        entry = [priority, item]
        if item in self.entry_finder:
            self.remove(item)
        self.entry_finder[item] = entry
        heappush(self.queue, entry)

    def remove(self, item: T) -> None:
        """Marks the entry corresponding to the item as removed"""
        entry = self.entry_finder.pop(item)
        entry[1] = self._REMOVED
