"""The four diagrams the review deck needs, as hand-drawn scenes.

Run:  python docs/report/sketch_figures.py
"""

from sketch import BLUE, CREAM, GREEN, GREY_T, RED, TEAL, VIOLET, WHITE, Scene


# ══════════════════════════════════════════════════ 1. system architecture
def architecture():
    # Deliberately wide (1600x780, roughly 2:1). A 4:3 diagram on a 16:9 slide
    # is height-constrained, so it shrinks to about a third of the slide width
    # and the labels stop being readable from the back of a room. Spreading the
    # same five bands sideways lets it fill the slide it actually has to live
    # on.
    s = Scene("arch", 1600, 780,
              title="Errandly - System Architecture",
              subtitle="modular monolith over polyglot persistence")

    LEFT = 187
    s.text(25, 120, "CLIENTS", fs=18, color=GREY_T)
    for i, label in enumerate(("Mobile App\nReact Native",
                               "Web App\nReact + Vite",
                               "Admin Console\nfraud review")):
        s.box(LEFT + i * 440, 95, 400, 70, label, fs=19)
    for i in range(3):
        s.arrow(LEFT + 200 + i * 440, 165, LEFT + 200 + i * 440, 198)

    s.text(25, 225, "API", fs=18, color=GREY_T)
    for i, label in enumerate(("REST  ·  FastAPI", "WebSocket  ·  live",
                               "Push  ·  FCM / Expo")):
        s.box(LEFT + i * 440, 200, 400, 65, label, fs=19)
    s.arrow(LEFT + 640, 265, LEFT + 640, 298)

    s.text(25, 330, "DOMAIN", fs=18, color=GREY_T)
    domain = [("Auth &\nIdentity", WHITE), ("Errands &\nMatching", CREAM),
              ("Ledger &\nEscrow", CREAM), ("Social\nGraph", CREAM),
              ("Fraud\nDetection", CREAM), ("Chat &\nNotify", WHITE)]
    for i, (label, fill) in enumerate(domain):
        s.box(LEFT + i * 224, 300, 203, 82, label, fill=fill, fs=18)

    s.box(LEFT, 402, 1323, 58,
          "Offer Log  -  every candidate and every ranking term, per round",
          fill=VIOLET, fs=19)
    s.arrow(LEFT + 143, 460, LEFT + 143, 493)

    s.text(25, 525, "ASYNC", fs=18, color=GREY_T)
    async_row = [("Transactional\nOutbox", WHITE), ("Relay", WHITE),
                 ("Kafka\nconsumers", WHITE), ("Ollama LLM\non campus", VIOLET)]
    for i, (label, fill) in enumerate(async_row):
        x = LEFT + i * 351
        s.box(x, 495, 287 if i < 3 else 270, 68, label, fill=fill, fs=18)
        if i < 3:
            s.arrow(x + 287, 529, x + 349, 529)
    s.arrow(LEFT + 124, 563, LEFT + 124, 606)

    s.text(25, 635, "STORAGE", fs=18, color=GREY_T)
    for i, label in enumerate(["PostgreSQL\n+ PostGIS", "Redis\ngeo · locks",
                               "MongoDB\nchat", "Neo4j\nsocial graph",
                               "Kafka log\nevents"]):
        s.box(LEFT + i * 269, 606, 248, 72, label, fill=TEAL, fs=18)

    s.text(800, 712,
           "Shaded modules carry the novel contribution.  Neo4j is derived, "
           "rebuildable from PostgreSQL at any time.",
           fs=16, color=GREY_T, anchor="center")
    s.save()


# ═════════════════════════════════════════════ 2. trust: distance and time
def trust():
    # Wide, for the same reason the architecture diagram is: these sit in the
    # lower half of a 16:9 slide, so height is the scarce dimension.
    s = Scene("trust", 1600, 660,
              title="What a friendship is worth, and how fast it fades",
              subtitle="trust falls with distance - and with how NEW the "
                       "newest link on the path is")

    s.text(60, 120, "DISTANCE", fs=18, color=GREY_T)
    nodes = [("you", None, None), ("friend", 1.00, "1500 m"),
             ("friend of\na friend", 0.45, "675 m"),
             ("3 hops", 0.20, "304 m"), ("4 hops", 0.09, "137 m")]
    xs = [140, 420, 700, 980, 1260]
    for i, ((label, trust_v, metres), x) in enumerate(zip(nodes, xs)):
        s.ellipse(x, 135, 92, 92, "", fill=BLUE if i == 0 else WHITE)
        s.text(x + 46, 238, label, fs=18, anchor="center")
        if i > 0:
            s.line(xs[i - 1] + 92, 181, x, 181)
            s.text(x + 46, 300, f"{trust_v:.2f}", fs=24, anchor="center")
            s.text(x + 46, 338, metres, fs=17, color=GREY_T, anchor="center")
    s.text(140, 300, "trust", fs=18, color=GREY_T)
    s.text(140, 338, "head start", fs=17, color=GREY_T)

    s.box(90, 398, 620, 88,
          "Each hop keeps 45% of the last.\nPast four hops a path exists but "
          "means nothing.", fill=WHITE, fs=18)

    s.text(800, 392, "TIME  -  our contribution", fs=18, color=GREY_T)
    bars = [("made TODAY", 630, CREAM), ("after a week", 810, CREAM),
            ("after a month", 1500, GREEN)]
    for i, (label, metres, fill) in enumerate(bars):
        y = 420 + i * 56
        s.text(800, y + 10, label, fs=17)
        s.box(1030, y, metres / 1500 * 300, 44, f"{metres} m", fill=fill, fs=17)

    s.text(800, 600,
           "A friendship made this morning is worth 630 m, not 1500 m. "
           "The network cannot be bought in an afternoon.",
           fs=17, color=GREY_T, anchor="center")
    s.save()


# ══════════════════════════════════════ 3. honest group vs collusion ring
def ring():
    s = Scene("ring", 1600, 700,
              title="Two groups the structure cannot tell apart",
              subtitle="both are fully closed - only where the money goes "
                       "separates them")

    # Stops above the summary box: run past it and the divider strikes through
    # the sentence inside.
    s.line(800, 115, 800, 520, dashed=True, lw=1)

    s.text(400, 125, "HONEST FRIEND GROUP", fs=20, anchor="center")
    s.ellipse(290, 175, 78, 78, "A", fill=WHITE)
    s.ellipse(470, 175, 78, 78, "B", fill=WHITE)
    s.ellipse(380, 300, 78, 78, "C", fill=WHITE)
    s.line(368, 214, 470, 214)
    s.line(320, 253, 390, 300)
    s.line(508, 253, 448, 302)
    s.ellipse(170, 380, 68, 68, "S", fill=BLUE)
    s.ellipse(560, 380, 68, 68, "S", fill=BLUE)
    s.arrow(300, 253, 220, 380, dashed=True)
    s.arrow(515, 255, 580, 380, dashed=True)
    s.text(400, 472, "money LEAVES the group", fs=19, anchor="center")
    s.text(400, 502, "circulation  LOW", fs=18, color=GREY_T, anchor="center")

    s.text(1150, 125, "COLLUSION RING", fs=20, anchor="center")
    s.ellipse(1040, 175, 78, 78, "X", fill=RED)
    s.ellipse(1220, 175, 78, 78, "Y", fill=RED)
    s.ellipse(1130, 300, 78, 78, "Z", fill=RED)
    s.arrow(1118, 200, 1220, 200)
    s.arrow(1248, 253, 1190, 302)
    s.arrow(1120, 313, 1068, 253)
    s.text(1150, 412, "money RETURNS to its source", fs=19, anchor="center")
    s.text(1150, 442, "circulation  HIGH", fs=18, color=GREY_T, anchor="center")

    s.box(200, 540, 1200, 82,
          "Both score closure 1.0. The discriminator is a directed PAID cycle:\n"
          "3 or more people  ·  the loop goes round twice  ·  each leg is real",
          fill=VIOLET, fs=19)
    s.text(800, 645,
           "Structure alone flagged 6 of 6 entirely honest groups in "
           "simulation.", fs=17, color=GREY_T, anchor="center")
    s.save()


# ════════════════════════════════════════════════ 4. escrow and the ceiling
def escrow():
    s = Scene("escrow", 1600, 620,
              title="Locking money for a price nobody knows yet",
              subtitle="the bill only becomes real at the counter, hours "
                       "after the money is committed")

    s.box(120, 105, 1360, 58,
          "Rs 378 locked the moment the order is placed  -  Rs 300 estimate  "
          "+  16% headroom  +  Rs 30 fee", fill=BLUE, fs=19)

    s.line(200, 250, 1400, 250, lw=3)
    # Two lines of 17pt need ~44px of headroom above the tick.
    s.line(620, 222, 620, 278, lw=2)
    s.text(620, 176, "estimate\nRs 300", fs=18, anchor="center")
    s.line(940, 222, 940, 278, lw=2)
    s.text(940, 176, "ceiling\nRs 348", fs=18, anchor="center")
    s.box(620, 239, 320, 22, "", fill=CREAM, rounded=False, lw=1)
    s.text(780, 290, "the runner may spend anywhere in here", fs=16,
           color=GREY_T, anchor="center")

    outcomes = [
        ("Spends Rs 280", "Paid in full. Rs 20 goes back to the customer.",
         GREEN),
        ("Spends Rs 340", "Paid in full. Rs 8 goes back. Nobody is out of "
                          "pocket.", GREEN),
        ("Spends Rs 395", "Past the ceiling. Nothing moves - an admin decides.",
         RED),
    ]
    for i, (head, body, fill) in enumerate(outcomes):
        y = 340 + i * 68
        s.box(200, y, 280, 54, head, fill=fill, fs=19)
        s.box(510, y, 890, 54, body, fill=WHITE, fs=18)

    s.text(800, 566,
           "The customer can never be charged past the Rs 348 they agreed to. "
           "That line is where the system stops deciding on its own.",
           fs=17, color=GREY_T, anchor="center")
    s.save()


if __name__ == "__main__":
    print("drawing:")
    architecture()
    trust()
    ring()
    escrow()
