
from itertools import permutations
from math import radians, sin, cos, asin, sqrt


def haversine_km(a, b):
    la1, lo1, la2, lo2 = map(
        radians,
        (
            a["latitude"], a["longitude"],
            b["latitude"], b["longitude"]
        )
    )

    h = (
        sin((la2 - la1) / 2) ** 2
        + cos(la1) * cos(la2)
        * sin((lo2 - lo1) / 2) ** 2
    )

    return 2 * 6371 * asin(sqrt(h))


def plan_route(depot, stops):
    """Calculate shortest route returning to depot."""
    if not stops:
        return [], 0.0

    best_order = None
    best_km = float("inf")

    for order in permutations(stops):
        points = [depot, *order, depot]

        total = sum(
            haversine_km(points[i], points[i + 1])
            for i in range(len(points) - 1)
        )

        if total < best_km:
            best_order = list(order)
            best_km = total

    return best_order, round(best_km, 2)
