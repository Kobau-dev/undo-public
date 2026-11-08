import sys, time, Quartz
x, y = float(sys.argv[1]), float(sys.argv[2])
cur = Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))
for i in range(1, 21):
    t = i / 20
    e = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (cur.x + (x - cur.x) * t, cur.y + (y - cur.y) * t), 0)
    Quartz.CGEventSetFlags(e, 0); Quartz.CGEventPost(Quartz.kCGHIDEventTap, e); time.sleep(0.02)
print("hover", x, y)
