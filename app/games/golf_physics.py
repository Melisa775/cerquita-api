"""Top-down mini golf physics.

The course is 100 × 150 units. A shot is an angle and a power (0 to 1); it
is simulated step by step (240 steps per second) and the ball's path is
returned sampled at 60 frames per second so both browsers animate it the
same way. Since the simulation runs on the server, both players always see
the same thing.

Hole elements:
  walls    -> polylines; the ball bounces off them (losing a bit of speed)
  bumpers  -> circles that bounce harder
  sand     -> rectangles that slow the ball down a lot
  water    -> rectangles: the ball returns to where it was shot and a stroke is added
  slopes   -> tilted rectangles: they push the ball in one direction
  portals  -> entrance and exit: the ball pops out the other side at the same speed
"""

import math

BALL_R = 2.2
HOLE_R = 3.6
MAX_SPEED = 170.0
DT = 1 / 240
SAMPLE_EVERY = 4  # 60 frames per second
MAX_TIME = 14.0
FRICTION_CONST = 14.0
FRICTION_LINEAR = 0.35
SAND_FACTOR = 5.0
WALL_BOUNCE = 0.78
BUMPER_BOUNCE = 1.15
CAPTURE_SPEED = 58.0
PORTAL_R = 4.0


def _in_rect(x, y, rect) -> bool:
    rx, ry, w, h = rect[:4]
    return rx <= x <= rx + w and ry <= y <= ry + h


def _segments(course):
    for line in course["walls"]:
        for a, b in zip(line, line[1:]):
            yield a, b


def simulate(course: dict, start: tuple[float, float], angle: float, power: float) -> dict:
    """Simulate a shot. Returns the path, where it stopped and what happened."""
    power = max(0.0, min(1.0, float(power)))
    x, y = float(start[0]), float(start[1])
    vx = math.cos(angle) * power * MAX_SPEED
    vy = math.sin(angle) * power * MAX_SPEED
    hx, hy = course["hole"]
    segments = list(_segments(course))
    path = [[round(x, 2), round(y, 2)]]
    events = []
    portal_cooldown = 0
    result = "stopped"
    steps = int(MAX_TIME / DT)

    for step in range(1, steps + 1):
        # slopes
        for s in course.get("slopes", []):
            if _in_rect(x, y, s):
                vx += s[4] * DT
                vy += s[5] * DT
        # friction (constant + proportional to speed), stronger in sand
        speed = math.hypot(vx, vy)
        factor = SAND_FACTOR if any(_in_rect(x, y, s) for s in course.get("sand", [])) else 1.0
        dec = (FRICTION_CONST + FRICTION_LINEAR * speed) * factor * DT
        if speed <= dec:
            vx = vy = 0.0
        else:
            k = (speed - dec) / speed
            vx *= k
            vy *= k
        # the hole pulls the ball in a little when it passes slowly nearby
        dhx, dhy = hx - x, hy - y
        dist_h = math.hypot(dhx, dhy)
        if 0 < dist_h < HOLE_R * 1.8 and speed < CAPTURE_SPEED * 1.3:
            pull = 40.0 * DT
            vx += dhx / dist_h * pull
            vy += dhy / dist_h * pull

        x += vx * DT
        y += vy * DT

        # walls
        for (ax, ay), (bx, by) in segments:
            ex, ey = bx - ax, by - ay
            seg_len2 = ex * ex + ey * ey
            t = 0.0 if seg_len2 == 0 else max(0.0, min(1.0, ((x - ax) * ex + (y - ay) * ey) / seg_len2))
            qx, qy = ax + ex * t, ay + ey * t
            dx, dy = x - qx, y - qy
            d = math.hypot(dx, dy)
            if 0 < d < BALL_R:
                nx, ny = dx / d, dy / d
                vn = vx * nx + vy * ny
                if vn < 0:
                    vx -= (1 + WALL_BOUNCE) * vn * nx
                    vy -= (1 + WALL_BOUNCE) * vn * ny
                    if abs(vn) > 25:
                        events.append({"t": step // SAMPLE_EVERY, "kind": "wall"})
                x, y = qx + nx * BALL_R, qy + ny * BALL_R
        # bumpers
        for bx, by, br in course.get("bumpers", []):
            dx, dy = x - bx, y - by
            d = math.hypot(dx, dy)
            if 0 < d < br + BALL_R:
                nx, ny = dx / d, dy / d
                vn = vx * nx + vy * ny
                if vn < 0:
                    vx -= (1 + BUMPER_BOUNCE) * vn * nx
                    vy -= (1 + BUMPER_BOUNCE) * vn * ny
                    events.append({"t": step // SAMPLE_EVERY, "kind": "bumper"})
                x, y = bx + nx * (br + BALL_R), by + ny * (br + BALL_R)
        speed = math.hypot(vx, vy)
        if speed > MAX_SPEED:
            vx, vy = vx / speed * MAX_SPEED, vy / speed * MAX_SPEED
        # portals
        if portal_cooldown:
            portal_cooldown -= 1
        else:
            for px, py, qx, qy in course.get("portals", []):
                if math.hypot(x - px, y - py) < PORTAL_R:
                    speed = math.hypot(vx, vy) or 1.0
                    x = qx + vx / speed * (PORTAL_R + 1)
                    y = qy + vy / speed * (PORTAL_R + 1)
                    portal_cooldown = 60
                    events.append({"t": step // SAMPLE_EVERY, "kind": "portal"})
                    break
        # water
        if any(_in_rect(x, y, w) for w in course.get("water", [])):
            result = "water"
            break
        # hole
        if math.hypot(x - hx, y - hy) < HOLE_R - BALL_R * 0.3 and math.hypot(vx, vy) < CAPTURE_SPEED:
            x, y = float(hx), float(hy)
            result = "holed"
            break

        if step % SAMPLE_EVERY == 0:
            path.append([round(x, 2), round(y, 2)])
        speed = math.hypot(vx, vy)
        on_slope = any(_in_rect(x, y, s) and math.hypot(s[4], s[5]) > FRICTION_CONST for s in course.get("slopes", []))
        if speed < 1.0 and not on_slope:
            break

    path.append([round(x, 2), round(y, 2)])
    if result == "water":
        end = [float(start[0]), float(start[1])]
    else:
        end = [round(x, 2), round(y, 2)]
    return {"path": path, "end": end, "result": result, "events": events}
