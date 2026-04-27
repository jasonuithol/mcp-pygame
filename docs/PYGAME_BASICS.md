# pygame basics

This doc grows organically as patterns and gotchas accumulate. It's intentionally
skeletal at bootstrap — the knowledge base is expected to carry most of the
hard-won detail. Use `ask("...")` liberally.

## Event loop sketch

```python
import pygame

pygame.init()
screen = pygame.display.set_mode((640, 480))
clock = pygame.time.Clock()

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
    # update + draw
    clock.tick(60)

pygame.quit()
```

## Headless init for tests

Set env vars before `pygame.init()`:

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
```

The `mcp-build` container sets these for `run_tests` automatically.

## Surface vs Rect

`Surface` holds pixels; `Rect` holds geometry. `blit(source, dest)` where
`dest` can be a `Rect` (only the top-left is used) or an `(x, y)` tuple.

---

Ask the knowledge base for anything more specific — `ask("Surface blit alpha")`,
`ask_tagged("collision", ["sprite"])`, etc.
